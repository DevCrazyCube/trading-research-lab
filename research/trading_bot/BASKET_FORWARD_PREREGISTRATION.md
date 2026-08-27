# BASKET FORWARD PRE-REGISTRATION — the imperfect-edge basket, forward paper LOGGER

**Written and frozen 2026-08-20, before a single forward observation exists.** That timing is the
whole point. Every backtested number attached to these legs is an **upper bound on the truth**,
inflated by exactly the selection the DSR/power gates exist to catch. This document freezes the
basket — its legs, universes, signals, execution assumptions, sizing sleeve, cost models, the
benchmark, and the per-leg kill switch — so that the forward log it governs measures **realised
out-of-sample edge**, not a re-fit. A rule that can move after the data prints is not frozen, and a
forward test of an unfrozen rule measures nothing.

Companion: `research/trading_bot/IMPERFECT_BASKET.md` (the audit that produced this candidate set,
with the honest caveats), `T3_RERUN.md` (the anchor leg's realistic-execution number),
`ORIGINAL_STRATEGY_SHORTLIST_BROAD.md` §3 (the ETF-sibling RV leg), and
`ITERATION_PROTOCOL.md` (how this test is allowed to change — the answer is: it is not, except by
standing up a NEW frozen test).

---

## 0. WHAT THIS IS, AND — LOUDLY — WHAT IT IS NOT

This is a **LOGGER**. It computes each leg's signal from data available as-of a session close,
marks the resulting **hypothetical** position to the next realised prices, and appends a
per-leg + combined mark-to-market P&L row to an append-only forward log. It is the T16-panel
pattern: a **pure forward recording instrument**.

- **NO orders are ever placed** — not live, not paper. There is no broker-auth file, no order
  endpoint, no `submit` mode anywhere in `basket_forward.py`. The only network it touches is the
  Alpaca **market-data** host (read-only), through the same `data.py` guard the backtest rig uses.
- **NO real money. NO position is ever held.** Every P&L number in the log is hypothetical-but-honest
  mark-to-market: "if the frozen rule had traded this session at the modelled prices and costs, this
  is the net it would have realised." The log is the evidence; it is not yet evidence of anything.
- **This measures realised edge to defeat selection bias.** The honest prior, stated once here so it
  is not discovered in month six: the backtested standalone Sharpes are ~1.0–1.3, and the candid
  expectation for the **realised** combined forward Sharpe is **well below that — ~0.3–0.6, and it
  could be zero.** Two of the legs are correlated (both overnight-equity is not the basket; see §6),
  every point estimate is a search-inflated upper bound, and the capacity-tiny legs cannot carry much
  risk. The basket is a way to *find out* whether several weak positives survive a clean window — not
  a reason to believe any of them.

---

## 1. THE LEGS — live at freeze vs pending

The basket is pre-registered with **four return-leg slots and one sizing overlay**. Two legs are
**ACTIVE** at freeze (fully specified, data reachable on free Alpaca SIP). Two are **PENDING_SPEC**:
their slot, family, risk budget and kill rule are frozen here, but their exact signal is declared
`null` and the logger will not trade them until a follow-up freeze fills the spec in. A PENDING leg
contributes nothing to the combined P&L and cannot be silently switched on.

| slot | leg | family | horizon | status at freeze |
|---|---|---|---|---|
| L1 | **T3 end-of-day pressure reversal** (anchor) | overnight cross-sectional reversal | close(t) → open(t+1) | **ACTIVE** |
| L2 | **ETF-sibling relative value** (Arm B) | identical-claim market-neutral RV | 15:45(t) → close(t) | **ACTIVE** |
| L3 | dual-class voting-premium RV | identical-claim market-neutral RV | (to be declared) | **PENDING_SPEC** |
| L4 | T7 ex-dividend overnight residual | ex-dividend overnight event | cum-close → ex-open | **PENDING_SPEC** |
| Sleeve | **T13 vol-targeting overlay** | market-beta sizing | — | **ACTIVE** (sizes the aggregate) |

### L1 — T3 end-of-day pressure reversal (ACTIVE, anchor)

- **Universe:** top **300** US common stocks by trailing dollar ADV (the milder-tailed variant
  recommended by `T3_RERUN.md` §4: kurtosis 9.4 vs 12.3 for top-500, same edge). Point-in-time
  monthly screen exactly as `scripts/t3_pressure_reversal.py::build_universe(300)`: month *m* trades
  the set ranked by month *m−1*'s raw dollar ADV, price > \$5, ADV > \$20 M.
- **Signal (as-of close(t)):** for each name compute the last-10-minute move `r10 = P(15:59)/P(15:49) − 1`.
  Rank cross-sectionally. The **long** decile is the `cut = 0.10` most-negative `r10` (fade by buying);
  the **short** decile is the `cut = 0.10` most-positive (fade by selling). Dollar-neutral: 50% long
  the long decile, 50% short the short decile, equal-weight within each.
- **Execution (frozen, realistic — T3_RERUN §2-3):** entry is a marketable order at ~15:59 that pays
  one measured quoted half-spread; exit is the next session's **opening auction** (MOO), marked at the
  official opening print `po` (M0: 99.96% print rate, top-500, single-price cross = zero spread).
- **Mark:** realised overnight return per name `po(t+1)/P59(t) − 1`; leg net =
  `0.5·mean(long) − 0.5·mean(short) − cost` (see §4). One **night** = one observation.
- **Exclusions (identical to the frozen T3 panel):** drop a name whose exit date carries any corporate
  action; drop a night with < 100 surviving names; require the 15:49, 15:59 minute closes and the
  next-open auction print.
- **Prior verdict:** ALIVE for a small forward test — net **+5.04 bp/night, t +2.57, OOS Sharpe 1.21**,
  bootstrap P(mean≤0)=0.46%, permutation p=0.0001; killed only on **DSR 0.917 < 0.95** (a *certainty*
  miss). Declared trials in the T3 family: **8** (the frozen grid; "certainly an undercount").

### L2 — ETF-sibling relative value, Arm B (ACTIVE)

- **Universe (same-claim pairs only, post-census §3.2a of the broad shortlist):** 5 independent
  spreads across 4 index factors, each pair being two wrappers on the **identical** index:
  `(IVV,SPY)`, `(VOO,SPY)` [S&P 500], `(QQQM,QQQ)` [Nasdaq-100], `(VTWO,IWM)` [Russell 2000],
  `(IJH,MDY)` [S&P MidCap 400]. All clear the liquidity/coverage screen (median closing print
  ≥ \$1 M, code-agnostic official close). Thin wrappers (SPLG, VOOG, VONE, VTHR, VIOO, SPSM, …) are
  excluded — they are puddles, not rails.
- **Signal (as-of 15:45(t)):** for pair `(A,B)`, `s_t = ln(P_A/P_B)` at 15:45; standardise against the
  **trailing 60 sessions'** 15:45 log-spread (window ends at session *t−1*): `z = (s_t − mean_60)/sd_60`.
  Trade fires when `|z| ≥ 1.5`; the position **fades** the dislocation — long the cheap wrapper, short
  the rich — dollar-neutral within the pair. No fire ⇒ flat that pair that session.
- **Execution (Arm B, frozen):** entry at the 15:45 continuous price crossing each leg's half-spread;
  exit at the **same-session 16:00 closing print** (single-price cross, zero spread) + SEC §31 on the
  sold notional. **Fifteen-minute horizon, no overnight gap.**
- **Mark:** realised pair return `sign(−z)·[ (Pc_A/P45_A − 1) − (Pc_B/P45_B − 1) ] − cost`, averaged
  over the pairs that fired. One **session** (the day's fired-pair book) = one observation.
- **Distribution screen:** drop any pair-session within ±1 session of either leg's ex-distribution
  date (raw auction/continuous prices manufacture fake dislocations otherwise).
- **Prior:** not yet run out of sample; honest expected gross **1.7–2.2 bp/pair-session**, net
  **1.0–1.5 bp**, market-neutral. Expected to die on its own gate ~70% of the time. Declared trials in
  this family: **2** (Arm A auction-to-auction and Arm B; only Arm B is traded here, both counted).

### L3, L4 — PENDING_SPEC

Frozen: the slots exist, carry the risk budgets in §5, and are governed by the same kill switch. Their
signal is `null`. Turning either on requires a **new** pre-registration freeze that fills the spec and
bumps this document's version — never an in-place edit (ITERATION_PROTOCOL §4).

### Sleeve — T13 vol overlay (ACTIVE, sizes the aggregate, is NOT a return leg)

`w_vol = min(1.0, 0.10 / realised_vol_60(SPY))`, realised vol = annualised stdev of the last 60 daily
SPY total-return closes, **using closes through session t−2** (T13-L1, enforced by the fetch window,
not by an assertion). This scales the **whole basket's** gross risk down when trailing vol rises. It is
the exact frozen T13 rule (`research/trading_bot/T13_FROZEN_CONFIG.json`,
`rule_id T13-VOL-L60-T0.1-WMAX1.0`), consumed from `scripts/t13_risk_shaping.vol_exposure`, never
retyped, and cross-checked against an independent recomputation each run.

---

## 2. AS-OF DISCIPLINE / THE LOOKAHEAD ASSERTION

The one failure this whole programme exists to prevent, arriving through the data layer, is a signal
that peeks at the price it is about to earn. Enforced, not promised:

1. **Every leg's signal inputs carry a strictly-earlier timestamp than its mark.** L1: signal minutes
   (≤ 15:59 of session *t*) precede the mark (open auction of *t+1*). L2: signal (15:45 of *t*) precedes
   the mark (16:00 close of *t*). The logger asserts `max(signal_ts) < min(mark_ts)` per leg and
   **refuses** on violation.
2. **The vol overlay uses closes through *t−2* only** — enforced by ending the SPY daily fetch window
   before the session, as in T4; a bar dated on or after the session refuses.
3. **No forward row before the freeze.** The logger refuses to log any session dated **before**
   `freeze_utc`'s date. A session before the freeze is in-sample by construction and may only be run in
   the labelled, non-ledger `proof` mode (a wiring check, explicitly not evidence).
4. **The trailing-60 spread window for L2 ends at *t−1*.** The 15:45 spread of session *t* is compared
   only to sessions strictly before it.

---

## 3. TIMING, AND WHY A SESSION SETTLES WHEN IT DOES

- **L2 (intraday)** settles the **same session** its signal is formed: 15:45 → 16:00 close, both on *t*.
  Its forward observation is complete as soon as *t*'s close prints.
- **L1 (overnight)** is a two-phase decision: the signal is formed at close(*t*) and queued
  `pending`; it settles only once open(*t+1*) prints, on a later run. A night whose exit auction has
  not printed stays pending and accrues nothing — a phantom mark is never fabricated.
- A run may therefore append: L2 settled + L1 pending (fresh signal), and/or L1 settlements bound from
  earlier pending nights. The combined row for a session is written only for sessions whose L2 mark and
  any bound L1 mark have realised; a still-pending L1 night is recorded but excluded from the combined
  return until it settles.

---

## 4. COST MODELS — per side, sourced, every number an upper-bounded LOWER bound on friction

All costs are charged against the leg's hypothetical book; a zero is a *measurement* (auction cross) or
a stated lower bound, never a missing number.

**L1 (T3), per night, on the realistic rail of `T3_RERUN` §3:**

| item | value | source |
|---|---|---|
| entry half-spread (marketable at 15:59) | **1.43 bp** on 100% notional | T3 measured quoted median half-spread, top-300 |
| exit (MOO opening auction) | **0.00 bp** | M0 single-price cross, 99.96% print rate top-500 |
| SEC §31 + FINRA TAF (sold notional, round trip) | **0.31 bp** | T10-derived; `costs.py` fee convention |
| stock-borrow on the 50% short notional | **30 bp/yr** × calendar-gap/365.25 | `retail_taker_costs` GC default |

Net night bp = gross − 1.43 − 0.31 − 0.5·(30bp)·gap/365.25.

**L2 (ETF-sibling RV, Arm B), per pair-session, both continuous entries + auction exit:**

| item | value | source |
|---|---|---|
| entry half-spread, leg A + leg B (15:45 continuous) | frozen per-symbol table below (bp) | broad shortlist §2d / §3.7 |
| exit (16:00 closing auction, both legs) | **0.00 bp** | M0 single-price cross |
| SEC §31 (sold notional, ~2× leg) | **0.278 bp** × sold turnover | T10 |

Frozen per-symbol 15:45 half-spread (bp): `SPY 0.13, IVV 0.35, VOO 0.35, QQQ 0.15, QQQM 0.50,
IWM 0.20, VTWO 0.50, MDY 0.40, IJH 0.40`. A pair's entry cost is `hs_A + hs_B` (each leg crossed).

Every settled row also logs a **taker-rail stress cost** (`retail_taker_costs`, 2.5 bp/side)
beside the primary rail, so the accrual carries its own sensitivity to the one cost assumption it
leans on.

---

## 5. SIZING — capacity-first, risk-parity across return SOURCES, tiny in dollars

The purpose is to **generate honest observations, not P&L.** Sizing (from `IMPERFECT_BASKET.md` §3d):

- **Risk budget across the return SOURCES, not the legs.** The two overnight-correlated sources
  (L1, and L4 when live) share **one** budget; each market-neutral RV source (L2, L3) gets its own.
  At freeze, with L1 and L2 active and L3/L4 pending, the active split is **L1 : L2 = 0.50 : 0.50** of
  the deployed risk sleeve. When L3/L4 activate, the frozen target is **overnight(L1+L4) 1/3 :
  ETF-RV(L2) 1/3 : dual-class(L3) 1/3**, L4 sharing L1's third at half diversification credit.
- **One vol overlay on the aggregate.** Deployed gross = `w_vol × Σ_active budget`. Idle capital
  (`1 − deployed`) earns the **T-bill** rate (SGOV/BIL proxy = FRED DTB3), and most of a \$100 k book
  stays in T-bills — prudent for an unproven book and the correct benchmark.
- **Combined book daily net** = `w_vol · Σ_L b_L · r_L,net  +  (1 − w_vol·Σ b_L) · r_cash`, where
  `b_L` is leg L's risk-budget fraction and `r_L,net` its net return on its own self-financing
  long/short book. The combined equity curve compounds this; the **benchmark** curve compounds
  `r_cash` alone. Dollar caps are set by measured auction capacity (§ IMPERFECT_BASKET 3d) and are a
  few \$k per RV leg — but because sizing is about observation count, the logger tracks **returns**
  (bp on a unit book), not dollars.

---

## 6. THE BENCHMARK AND THE COMBINED GATE

- **Benchmark from day one: by-year T-bills** (DTB3), compounded daily on idle plus the whole book's
  hurdle. An unlevered market-neutral book must beat **T-bills + 1.00 pp/yr** to count (the T23/T25
  bar); a book that merely beats zero has lost to cash.
- **Combined series gate (read only after the §7 minimum):** net mean per observation **> 0 at t > 2.80**
  AND **DSR ≥ 0.95** at the declared combined trial count (= number of legs ever stood up in this
  basket family, currently 2, rising as slots activate — retired legs still count, forever).
- **Diversification honesty:** L1 and L4 are both overnight close→open and positively correlated; the
  basket is **three roughly-independent risk sources, not five** (overnight, ETF-RV, dual-class). The
  combined √N credit is taken at three, not the leg count.

---

## 7. MINIMUM SAMPLE, KILL SWITCH, AND RETIREMENT — frozen before any datum

### 7a. Per-leg KILL SWITCH (the pre-registered drop rule)

A leg accrues a stream of settled net returns `{r_i}` (one per observation: L1 a night, L2 a session).
Let `n_L` be its settled count, `mean_L` the sample mean net, `se_L = sd/√n_L`.

> **A leg is DROPPED when, after `n_L ≥ N_min = 40` settled observations, its one-sided upper 95%
> confidence bound on the mean net is below zero:  `mean_L + 1.645·se_L < 0`.**

That fires only when the leg is **significantly negative** (per-observation t < −1.645) — it will not
prematurely kill a true-but-noisy positive, and it will catch a leg that is genuinely losing net of
cost. `N_min = 40` is ~two months of sessions for either leg. A dropped leg is **DEAD — significantly
negative forward**, its ledger is closed (never deleted), it keeps counting toward the family's DSR
trial number forever, and its risk budget is **not** reallocated to the survivors (reallocating on a
forward outcome is a search).

**Secondary retirement (not a kill, a verdict of "unproven"):** after `N_max = 500` settled
observations a leg that has never reached net `t > 2.80` is retired **UNPROVEN — did not certify**;
the honest expectation is that most legs end here, exactly as the audit warned.

### 7b. Combined minimum before any verdict

No pass/dead verdict on the **combined** basket is issued before **each active leg has ≥ N_min = 40
settled observations AND the combined series has ≥ 252 settled sessions** (one year). Below that the
log records behaviour, not evidence. FG-style fidelity and lookahead checks are read every run; the
edge gates (§6) are not read early.

### 7c. What may and may not change (ITERATION_PROTOCOL, restated)

- **Immutable:** every leg's universe, signal, execution rail, cost model, the sizing rule, the
  benchmark, the kill thresholds, the minimum sample. Changing any is a **new** frozen test.
- **Maintenance (allowed, logged):** fixing a crash/retry/timeout, refreshing the DTB3 cash series,
  a data-vendor bar the vendor itself revised, adding a read-only metric to the evaluator.
- **Forbidden:** editing a running leg's rule, restarting/truncating the ledger, reading a gate before
  its minimum, reallocating a killed leg's budget, activating a PENDING leg without a new freeze,
  extending a minimum after seeing the data, promoting anything to real money (owner-gated; this
  logger does not reach it and places no orders at all).

### 7d. STANDING PRE-REGISTRATION RULE — the ρ1(Δspread) measurement-error gate on FUTURE RV legs

**Added 2026-08-21 (v7). This is documentation of a FORWARD rule; it changes no existing leg.** A low
Hurst exponent and an ADF rejection are **necessary but not sufficient** for a relative-value spread
to be tradable: a spread that is nothing but **bid-ask / non-synchronous measurement error** also has
Hurst well below 0.5 and reverts fast, yet is untradable because the "reversion" is the half-spread
bouncing (`OU_MEAN_REVERSION.md`; `DEEPMINE_crosslist`). The discriminator is the **lag-1
autocorrelation of the spread's daily CHANGE, ρ1(Δs)**: a pure measurement-error spread has
`ρ1(Δs) → −0.50`; a genuine slow convergence sits well above that.

> **RULE (binding on any FUTURE relative-value leg before it may be frozen):** a candidate RV spread
> must have **`ρ1(Δs)` meaningfully above −0.5 — concretely `ρ1(Δs) > ≈ −0.35`, i.e. NOT
> bounce-dominated — in ADDITION to Hurst < 0.5 and an ADF rejection.** If the spread's daily change
> has `ρ1 < ≈ −0.35`, the "mean reversion" is measurement error and the candidate is **dead on
> arrival, whatever its Hurst or ADF says**, and it may not be stood up as a leg.

This gate is applied **before** a candidate's OU half-life or Hurst is even looked at. It is the
cleanest single explanation for why the live L2 leg's crude `|z|≥1.5` band fails out of sample
(its raw 15:45 spread has `ρ1(Δs) ≈ −0.5`), and it retroactively kills the metal-sibling
(GLD/IAU, SLV/SIVR) and cross-listing tethers already tested. It binds future freezes only; the
existing legs are unchanged.

### 7e. STANDING METHODOLOGY RULES — two null-construction corrections (binding on all FUTURE work)

**Added 2026-08-22 (v8), from `INVENT_0822B_MASTER.md` §4. Documentation of forward rules; changes no
existing leg.** Two null/artefact-construction mistakes were diagnosed this round and are recorded as
standing rules so they are never rebuilt.

1. **The "rotate-the-returns" size-matched placebo is BROKEN — do not build or rebuild it for a
   cross-sectional book.** Holding a dollar-neutral weight matrix fixed and rotating the return panel
   circularly *looks* perfectly size-matched, but coins **not yet listed** at the rotated date have no
   return, so the book **silently acquires a directional leg**: measured mean |net dollar exposure
   among names with a live return| = **0.0036 real vs 0.1284 rotated**. That injected directional
   exposure reports a placebo p95 at ~10.8 SD and **would have falsely killed a true survivor**. The
   **correct** cross-sectional null is to **permute the SIGNAL across the day's ADV-rank slots** — one
   permutation per replicate: slot *j* is nearly the same coin day-to-day, so persistence, turnover,
   neutrality and cross-sectional return covariance all survive, and **only signal-to-coin alignment
   is destroyed.** RULE: any cross-sectional placebo null MUST use ADV-slot signal permutation, never
   return rotation with a fixed weight matrix.

2. **The ρ1 mirror artefact produces fake MOMENTUM on averaged-price rails, not only fake reversion —
   kill it with a one-day-gap re-entry test.** `ρ1(Δspread)` catches bid-ask *bounce* (fake
   **reversion**), but the mirror image threatens a **VWAP / time-averaged-price** book: averaged-price
   returns carry `ρ1 = +0.193` (theory +0.25), manufacturing fake **momentum**. Both artefacts are
   lag-1 and both are neutralised by a **one-day gap** — signal through the close of day *t−1*, entry
   at the VWAP of day *t* — which puts signal and P&L **two lags apart**. Verified on synthetic panels
   with no effect planted: pure bounce gives +36.7 SR with no gap and −0.32 with the gap; pure
   time-averaged price gives +31.9 with no gap and −0.55 with the gap; a planted 8 bp effect is
   recovered at +2.73 through the gap. RULE: for any averaged-price (VWAP / TWAP) rail, add the
   mirror gate — a **one-day-gap re-entry test** must leave the edge intact — to the standing checklist
   *in addition to* the §7d `ρ1(Δs)` reversion gate.

---

## 8. CLAIMS THIS LOG MAY NEVER SUPPORT

- that any leg, or the basket, makes money;
- that the basket beats T-bills, before §7's minimum is met;
- any Sharpe, CAGR, information ratio, hit rate or p-value computed before the minimum, outside an
  explicit `inputs_that_are_not_results` block;
- that a calm stretch is evidence about any leg's edge;
- that this paper log is a reason to fund a live account. **Live execution is owner-gated, and this
  instrument is a logger that places no orders — it cannot promote itself.**

---

## 9. THE HONEST EXPECTATION, IN ONE PARAGRAPH

If every leg realises its (upper-bound) point estimate and the RV legs are genuinely uncorrelated with
the overnight legs, three independent selection-haircut-Sharpe-~0.6 sources combine to ~0.6·√3 ≈ 1.0.
That is the optimistic number and it is almost certainly too high: selection inflates each estimate,
two legs are correlated, the RV legs are capacity-tiny, and L3/L4 are in-sample/unspecified. The candid
expectation for the **realised** forward Sharpe is **~0.3–0.6, and it could be zero.** This log exists
to find out which — at the cost of a few \$k of *hypothetical* paper risk and no certainty borrowed
from any single backtest.

---

---

# APPENDIX A — FOLLOW-UP FREEZE (v2), 2026-08-20: L3/L4 filled, L5/L6 added

**Frozen 2026-08-20T20:00:00Z, before a single forward observation exists for any of these four
legs.** This is the follow-up freeze the reserved-slot mechanism (§1, §7c) requires: it fills the
`PENDING_SPEC` slots **L3 (DUALCLASS)** and **L4 (T7)** with their now-measured specs, and adds two
genuinely new frozen legs **L5 (T12CEF)** and **L6 (ORB)** from `THOROUGH_REEXAM.md`'s revive list.

The original **L1 (T3) and L2 (ETFRV) specs are UNCHANGED** — their objects in
`BASKET_FORWARD_FROZEN.json` are byte-identical to the v1 freeze and carry no per-leg hash. Each of
the **four** legs below is frozen with **its OWN `spec_sha256`** (a SHA-256 over that leg's canonical
JSON spec object, excluding the hash field), which the logger recomputes and verifies on every run.
The document-level `preregistration_sha256` is re-pinned to this extended .md — the version bump the
mechanism calls for, **not** an edit to any running leg. No forward row is logged for a leg before its
own `freeze_utc`; before that, only the labelled non-ledger `proof` mode may run it.

**Everything in §0 still governs: this is a LOGGER. No orders, no real money, no position, market-data
host + one keyless CEFConnect GET only.** Every held-out number quoted per leg is a
**selection-inflated UPPER BOUND** (four of these were revived on windows already spent); the forward
log is the only arbiter. The realised-Sharpe prior for the combined basket remains **~0.3–0.6 and
could be zero**.

### The extended basket

| slot | id | family | horizon | status | budget | own sha256 |
|---|---|---|---|---|---|---|
| L1 | T3 | overnight X-sectional reversal | overnight | ACTIVE (v1) | 0.25 | — (v1) |
| L2 | ETFRV | identical-claim RV | intraday | ACTIVE (v1) | 0.20 | — (v1) |
| L3 | DUALCLASS | identical-claim RV | multi-day | **ACTIVE** | 0.13 | `fa67c73f…` |
| L4 | T7 | ex-dividend overnight event | overnight | **ACTIVE** | 0.07 | `e12cb470…` |
| L5 | T12CEF | CEF discount convergence | 4-week | **ACTIVE** | 0.30 | `c60ceb57…` |
| L6 | ORB | intraday directional (probe) | intraday | **ACTIVE** | 0.05 | `b875c2fc…` |

**Risk budgets (§5 restated for six legs, `risk_budgets_active_v6`):** three roughly-independent
sources plus a tiny directional probe — overnight (T3+T7) 0.32 : identical-claim RV (ETFRV+DUALCLASS)
0.33 : CEF (T12CEF) 0.30 : ORB probe 0.05, summing to the deployed sleeve = 1.0 before the vol
overlay. L4 shares L1's overnight source at half diversification credit; L6 is capped **below** every
market-neutral leg. The **combined `declared_trials_now` rises 2 → 6** (killed/retired legs keep
counting forever), mechanically raising the DSR bar. The T13 vol overlay is unchanged and still sizes
the aggregate; the T-bill benchmark and per-leg kill switch (N_min=40, drop at upper-95% < 0) apply to
all six.

---

## L3 — DUALCLASS voting-premium RV (fills the reserved slot) · `spec_sha256 fa67c73f…`

- **Universe:** 16 liquid dual-class pairs (identical cash-flow claims): GOOGL/GOOG, BRK.A/BRK.B,
  FOXA/FOX, NWSA/NWS, UAA/UA, HEI/HEI.A, CWEN/CWEN.A, LGF.A/LGF.B, CENTA/CENT, LBRDA/LBRDK,
  LSXMA/LSXMK, FWONA/FWONK, Z/ZG, DISCA/DISCK, PBR/PBR.A, LILA/LILAK.
- **Signal (two-timescale z-fade):** `s = ln(P_A/P_B)` on **raw** daily closes; z = `(s − mean_L)/pstdev_L`
  over the trailing **L = 250** raw log-spreads (population sd). Enter when flat and `|z| ≥ K = 2.0`,
  dollar-volume ≥ \$1 M, both raw closes ≥ \$2. `z>0` ⇒ A rich ⇒ **short A / long B**; `z<0` ⇒ **long
  A / short B**; \$1 per leg, dollar-neutral. Exit at `|z| ≤ 0.5`, or **20** trading days, or series
  end. A day-over-day log-spread jump `> 0.15` is a **structural break**: the level window resets and
  any open position is abandoned uncounted. **P&L on split/dividend-adjusted closes.** One completed
  round-trip = one settled observation.
- **Cost:** `2·(hs_A + hs_B) + 2·0.278 bp (SEC §31 per sale) + borrow·hold/252`, per-symbol measured
  half-spreads (frozen table in the JSON), borrow 33 bp/yr ETB.
- **MANDATORY GUARD (easy-to-borrow short leg):** a round-trip whose **short** leg is not
  easy-to-borrow is **DROPPED**. At HTB rates (~1028 bp/yr) this edge is **−45 bp** — the frozen spec
  excludes HTB names by construction. Frozen ETB whitelist (24 of 32 symbols; excludes BRK.A, CWEN.A,
  LGF.A, LGF.B, LSXMA, LSXMK, DISCA, DISCK) captured 2026-08-20 to
  `research/data/t28_dualclass_cache/etb_flags_frozen.json` — an executability bound applied forward,
  not a historical screen.
- **Prior (upper bound):** RAW 16-subset **+18.36 bp/round-trip, t 2.13, n 201**, book Sharpe 0.99;
  under the frozen ETB guard **+12.68 bp, t 1.31, n 165** on the cached held-out window. 4.2× design→
  held-out shrinkage; declared trials 18.

## L4 — T7 ex-open dividend residual (fills the reserved slot) · `spec_sha256 e12cb470…`

- **Universe:** top-500 ADV US common (price > \$5, ADV > \$20 M, `include_special`, yield cap 0.20),
  eligible in **both** the cum-month and ex-month.
- **Signal:** for each cash dividend, cum-day = the session immediately before `ex_date`. Long the
  ex-div name from the **cum-day closing auction** to the **ex-date opening auction**; per-event return
  `(ex_open − cum_close + rate)/cum_close`. Portfolio `g = 0.5·mean(events) − 0.5·r_spy`,
  `r_spy = SPY(ex_open)/SPY(cum_close) − 1` (50 % short SPY hedge, dollar-neutral). A non-ex-div
  control (`0.5·mean(pool) − 0.5·r_spy`) is **watched, not traded**. One ex-date event-day = one
  observation. Exclusions: other corporate action on cum/ex, SPY ex-div, early close, missing auction
  print, `rate/cum_close > 0.20`.
- **Execution:** enter MOC on cum-day (`tif=cls`, before 15:50 ET; no intraday signal so the cutoff is
  free), exit MOO on ex-date (`tif=opg`), **M0-verified single-price auction rail, hs = 0** (99.96 %
  open-print coverage top-500-ADV).
- **Cost:** `SEC31·1.0 + TAF·0.5·(mean 1/p_cum + mean 1/p_exopen) + TAF/spy_price +
  0.5·borrow·gap/365.25`; SEC §31 0.278 bp, FINRA TAF 166 µ\$/share, borrow 33 bp/yr on the 50 % SPY
  short.
- **MANDATORY GUARD (satellite budget):** size SMALL (capacity ~\$100 k–\$600 k, ~6 names/night); it
  **shares L1's overnight session factor**, so it is budgeted as a satellite (0.07), never a second
  anchor. Taxable-account IRC §1211(b) stranding noted (irrelevant to a paper test).
- **Prior (upper bound, NOT out of sample — 2022–2026 was already looked at for this variant):**
  **+3.347 bp/event-day NET, t 2.96, n 1018**, ann Sharpe 1.38; net−control +3.263 bp (t 2.86);
  positive in both halves (design +2.25 bp, t 2.99). Full half-spread on all four legs → +0.487 bp
  (t 0.43). Declared trials 9. This is exactly why it belongs in a forward logger.

## L5 — T12 CEF discount-level tilt (NEW, highest priority, most diversifying) · `spec_sha256 c60ceb57…`

- **Universe:** the free, keyless **CEFConnect `/api/v3/DailyPricing`** snapshot (~360 live CEFs),
  screened to **price > \$5** and **borrowable-short** (Alpaca `easy_to_borrow=true`, frozen at
  `research/data/t12_cache/alpaca_assets.json.gz`). Live-only survivorship is recorded and runs
  plausibly conservative (liquidations pay near NAV).
- **Signal:** weekly discount snapshot (the `Discount` field = price vs NAV, negative = discount).
  Rank the borrowable price>\$5 universe by discount; **long ~36 widest-discount** names, **short ~36
  narrowest/premium** borrowable names, equal-weight, dollar-neutral. **4-week hold, weekly rebalanced
  as overlapping tranches** (¼ weight each; a name entered is held four weekly rebalances). One weekly
  rebalance's realised net portfolio return (the tranche completing its hold) = one settled
  observation.
- **Point-in-time NAV discipline:** the discount/NAV is used **only** to form the entry signal from
  the as-of snapshot; it is **never** used to mark. Marking is realised market **Price** only — no
  lookahead on NAV.
- **Execution rail:** Alpaca equities; the weekly discount fetch is **ONE keyless CEFConnect GET**
  (~620 KB, ~1 s) — inline-safe, not a crawl, no account/key. (Verified 2026-08-20:
  `/api/v3/DailyPricing` returns 200 with 360 rows carrying `Ticker`, `Discount`, `NAV`, `Price`.)
- **Cost:** 11.53 bp measured median CEF half-spread charged both sides on realised turnover, SEC §31
  0.278 bp on sold.
- **MANDATORY GUARD (realised short rate, not the ETB floor):** borrow on the short leg is charged at
  a **realised 200 bp/yr** — deliberately **above** the 33 bp ETB floor — and the borrowable-short
  screen keeps names executable; genuinely HTB premium-CEF shorts are excluded by the `easy_to_borrow`
  screen. Capacity SIZE-capped to low single-digit \$M (CEF closing auctions clear \$0.0–0.3 M).
- **Prior (upper bound):** **+13.44 bp/week NET, t 3.51, n 116 wk**, ann Sharpe 2.35; **DSR 0.9971 at
  the full 6 declared trials** (already deflated, above 0.95); permutation p 0.0005; block-bootstrap
  P(>0) 0.9999 over 29 independent rebalances; disjoint design 2021–2024 +13.85 bp/wk (t 3.11). Honest
  realised prior after survivorship + PIT-NAV + borrow haircuts **~1.0–1.5**. The best diversifier in
  the corpus (monthly CEF discount convergence, correlated with neither overnight equity nor
  identical-claim intraday RV) — and a live forward panel is the only instrument that fixes
  survivorship and PIT-NAV simultaneously.

## L6 — ORB no-stop residual (NEW, REDUCED / logging-only budget) · `spec_sha256 b875c2fc…`

- **Universe / selection:** point-in-time at 09:30 — raw open ≥ \$5, 14-session avg share volume ≥
  1 M, ATR(14 ending d−1) ≥ \$0.50; then relvol_pct ≥ 100 and a non-doji opening candle, sorted by
  `(−relvol_pct, symbol)`, **TOP 20** ("Stocks in Play"). **relvol_pct** = today's [09:30,09:35)
  volume as an integer % of that stock's trailing-14-session average opening-5-min volume (≥10 of 14
  prior obs required).
- **Signal:** opening range = the single **[09:30,09:35) ET 5-min bar** (OR_high = h, OR_low = l).
  **Long** if that candle closes above its open; **short** if below; doji skipped (one side only).
  Entry is a stop at the breakout level and **fills AT the breakout level** (adverse slippage charged
  in the cost model, not by a worse fill); never touched all session ⇒ **NO_TRIGGER** (no position).
  **Exit MOC** at the official closing print; **NO intraday stop** (deleting the stop deletes the exact
  leg that killed T18). Equal-weight **1/N over FIRED names, 1× gross**. One session = the
  equal-weighted mean of net per-name returns = one observation.
- **FROZEN conditioning:** the **unconditional** book (base screen + relvol ≥ 100 + top-20 *is* the
  conditioning). The relvol ≥ 500 % subset is **rejected** as post-hoc and non-monotone (0.43 at
  600 %, 0.54 at 700 %). Threshold and weighting are frozen here, in advance.
- **Cost:** entry slippage **9.02 bp** (T18 tick measurement vs the breakout level) + SEC/TAF 0.28 bp
  + **MOC exit 0** (measured −0.96 bp, favourable; 99.76 % official-print coverage). Net drag ≈ 9.30
  bp/trade. No borrow (intraday).
- **MANDATORY GUARD (reduced / logging-only):** the **weakest** revive — t 1.06 over 4.6 y, the
  unconditional book collapses to Sharpe 0.15 dropping the 2026 stub, and a no-stop book has an
  **unbounded intraday tail** (worst day −9.6 % at 1×). Risk budget capped **below** every
  market-neutral leg (0.05). A **hypothesis test, never fundable, never an allocation.**
- **Prior (upper bound):** held-out 2022–2026 (1158 sessions) **+4.81 bp/day NET, ann Sharpe 0.494,
  t 1.06** — reproduced **exactly** from the t17 cache under this frozen spec. Gross +14.11 bp/day; two
  of four full held-out years negative. Declared trials 16.

---

*Follow-up freeze appended 2026-08-20. Frozen instrument. No orders, no real money, no purchases, no
commit by the logger; free/cached data plus one keyless CEFConnect GET only. Every backtested number
herein is a selection-inflated upper bound; the forward log is the only evidence, and it is not yet
evidence of anything.*

---

---

# APPENDIX B — THIRD FREEZE (v3), 2026-08-20: L7 added (+ L8 unsized robustness sibling)

**Frozen 2026-08-20T22:00:00Z, before a single forward observation exists for either leg.** This
third freeze adds **one** genuinely new frozen leg — **L7 (XS_GLSR_Z)** — the single formula that
survived the 380-formula cross-theme sweep (`FORMULA_SWEEP_MASTER.md`): of 380 formulas across six
themes, exactly one clears the pooled noise bar on its design window, is net-positive out of sample
after realistic costs, survives a capacity cut, and is **not** already a BASKET1 leg. It also
pre-declares **L8 (XS_SMART)** — the same hypothesis's robustness sibling — **logged UNSIZED (zero
risk budget)**.

The original **L1–L6 specs are UNCHANGED** — their objects in `BASKET_FORWARD_FROZEN.json` are
byte-identical to the v1/v2 freezes. L7 and L8 are each frozen with **their OWN `spec_sha256`** (a
SHA-256 over that leg's canonical JSON object, excluding the hash field), which the logger recomputes
and verifies on every run. The document-level `preregistration_sha256` is re-pinned to this extended
`.md` — the version bump the reserved-slot mechanism (§1, §7c) requires, **not** an edit to any
running leg. No forward row is logged for a leg before its own `freeze_utc`; before that, only the
labelled non-ledger `proof` mode may run it, and L7's `proof` is a **cached held-out reproduction, NOT
ledger evidence.**

**Everything in §0 still governs: this is a LOGGER. No orders, no real money, no position.** L7/L8 add
**one read-only cached data source** — the frozen 1h Binance USD-M perp panel
(`research/data/perpmicro_cache/panel1h.npz`, built by `perpmicro_panel.py` from the orphanflush
cache: 5m klines + 5m metrics). The logger touches **no** exchange, no key, no crypto venue — only the
already-downloaded cache. Every held-out number below is a **selection-inflated UPPER BOUND**; the
forward log is the only arbiter, and the realised-Sharpe prior for the combined basket remains
**~0.3–0.6 and could be zero.**

### The extended basket (7 ACTIVE + 1 UNSIZED robustness logger)

| slot | id | family | horizon | status | budget (v7) | own sha256 |
|---|---|---|---|---|---|---|
| L1 | T3 | overnight X-sectional reversal | overnight | ACTIVE (v1) | 0.22 | — (v1) |
| L2 | ETFRV | identical-claim RV | intraday | ACTIVE (v1) | 0.18 | — (v1) |
| L3 | DUALCLASS | identical-claim RV | multi-day | ACTIVE (v2) | 0.11 | `fa67c73f…` |
| L4 | T7 | ex-dividend overnight event | overnight | ACTIVE (v2) | 0.06 | `e12cb470…` |
| L5 | T12CEF | CEF discount convergence | 4-week | ACTIVE (v2) | 0.27 | `c60ceb57…` |
| L6 | ORB | intraday directional (probe) | intraday | ACTIVE (v2) | 0.04 | `b875c2fc…` |
| **L7** | **XS_GLSR_Z** | **crypto-perp cross-sectional positioning** | **24h** | **ACTIVE** | **0.12** | `37418f23…` |
| L8 | XS_SMART | crypto-perp cross-sectional positioning | 24h | **ACTIVE_UNSIZED** | 0.00 | `28bb4edc…` |

**Risk budgets (§5 restated for the 7 sized legs, `risk_budgets_active_v7`, sum = 1.0).** L7 enters as
a **4th roughly-independent risk source** (crypto-perp cross-sectional — a different asset class,
venue, data source, horizon and 24/7 calendar; its design correlation to an equal-weight perp basket
is −0.01, so it is not crypto beta either). The four sources plus the ORB probe:

> overnight (T3 0.22 + T7 0.06) = 0.28 · identical-claim RV (ETFRV 0.18 + DUALCLASS 0.11) = 0.29 ·
> CEF (T12CEF) = 0.27 · **crypto-perp (XS_GLSR_Z) = 0.12** · ORB probe = 0.04.

The existing legs keep their v6 relative weights (each scaled by 0.88 to open L7's 0.12 sleeve). L7 is
sized **real-but-modest**: bigger than the ORB probe (0.04) and the T7 satellite (0.06), **smaller
than every anchor source** — honoring its thin deployable capacity (top-50 net Sharpe ~0.73), not the
top-120 upper bound. **L8 (XS_SMART) carries ZERO budget** and never touches the combined book. The
**combined `declared_trials_now` rises 6 → 7** (one new leg stood up; killed/retired legs keep counting
forever); L7 additionally carries **380 declared trials in its own leg family** (the full sweep), which
flows into that leg's own DSR. XS_SMART is the *same hypothesis* and adds no separate combined bite.
The T13 vol overlay is unchanged and still sizes the aggregate; the T-bill benchmark and per-leg kill
switch (N_min = 40, drop at upper-95% < 0) apply to all seven sized legs and to the unsized L8.

---

## L7 — XS_GLSR_Z crypto-perp account-positioning fade (NEW sized leg) · `spec_sha256 37418f23…`

- **Universe:** point-in-time **TOP-50** Binance USD-M perps by trailing-7d (168h) quote volume, at
  each 1h bar (finite signal, positive open, positive current-bar quote volume; ≥ 30 live names).
  **TOP-50 is the only universe where 5.5 bp/side is defensible** — the top-120 design universe is the
  full-universe upper bound, not the deployed one.
- **Signal:** `glsr = count_long_short_ratio` (Binance **global retail ACCOUNT** long/short ratio);
  `z = ` own-history z-score of `log(glsr)` over the trailing **168h (7d)**, causal (window ends at the
  close of bar t). **NEGATIVE sign / FADE:** short the names whose retail account positioning just
  spiked most long, long those that spiked most short. Cross-sectional **quintile** (long top 20% /
  short bottom 20%), demeaned dollar-neutral, gross normalised to 1. **24h hold.**
- **Execution:** holding at bar `j` = `mean(W[:, j−24 .. j−1])` (lag ≥ 1 bar, 24 overlapping
  tranches); bar return `= open[j+1]/open[j] − 1` (**open-to-open**; the close that formed the signal
  is never a fill price). Funding accrual charged/received at the bar a settlement lands in. One UTC
  day's realised net portfolio return = one settled observation.
- **Cost:** **5.5 bp/side** = 4.5 bp published Binance USD-M taker fee (VIP0, no BNB discount) + **1.0
  bp declared, never-measured** half-spread, on turnover. Breakeven cost per side is logged so it can
  be re-charged when perp slippage is measured.
- **MANDATORY GUARD (capacity / top-50 deployable):** the sized leg trades the top-50 ONLY;
  **deployable held-out net Sharpe ≈ 0.73** (+15.2%/yr), **−1.19 at a 15 bp/side shock**. `bookdepth`
  is in the cache and was not used, so capacity is untested beyond the volume screen — size modest.
- **AS-OF:** signal uses data through the close of bar t; weights are held from the open of t+1. The
  sweep's lookahead audit (destroy every input after the design cut, re-derive) reproduced
  bit-identical weights: **0 violations**.
- **Prior (UPPER BOUND):** full-universe (top-120) design gross 4.94 / net 3.37 / +49.4%/yr; held out
  (2024-04→2025-01, 275d, sign FROZEN from design) gross 3.92 / **net +2.38 / +34.5%/yr**, breakeven
  **14.0 bp/side**. **Deployable (top-50): net +0.73** (+15.2%/yr) at 5.5 bp/side. Cleared the
  380-formula pooled bar (3.44 Sharpe-SE) — the only formula of 380 to pass all three gates. One
  held-out regime only, no walk-forward. Declared trials **380**. The forward log is the arbiter.

## L8 — XS_SMART smart-vs-crowd spread (UNSIZED robustness sibling) · `spec_sha256 28bb4edc…`

- **Signal:** `smart = log(tts) − log(glsr)` = log(top-trader POSITION L/S) − log(global-account L/S).
  **Positive sign**, same top-50 universe, same quintile book, same 24h open-to-open rail and 5.5
  bp/side cost as L7.
- **MANDATORY GUARD (UNSIZED, zero risk budget):** recorded for **confirmation, not allocated**. Same
  hypothesis as L7 (both are Binance long/short-ratio fields). It **survives** the capacity cut
  (top-50 held-out net **+1.53**, +34.4%/yr; +0.80 at 15 bp/side) but **missed the pooled design bar**
  (gross 3.25 vs 3.36, by 0.11). If L7 forward-dies and L8 does not, that is **information, not a
  licence to swap** the sized leg (ITERATION_PROTOCOL: the answer is always a new frozen test).
- **Prior (UPPER BOUND):** top-50 held-out net Sharpe **+1.53**; design gross 3.25, net 2.74. Declared
  trials 380 (same hypothesis).

---

*Third freeze appended 2026-08-20. Frozen instrument. No orders, no real money, no purchases, no
commit by the logger; free/cached data only (one added read-only local cache: the frozen 1h perp
panel — no crypto venue, no key touched). Every backtested number herein is a selection-inflated upper
bound; the forward log is the only evidence, and it is not yet evidence of anything.*

---

*Frozen instrument. No orders, no real money, no purchases, no commit by the logger. Every backtested
number herein is a selection-inflated upper bound; the forward log is the only evidence, and it is not
yet evidence of anything.*


---

---

# APPENDIX C — FOURTH FREEZE (v4), 2026-08-20: L9 CEFMUNIEQ added; L7 XS_GLSR_Z DEMOTED to logging-only

**Frozen 2026-08-20, before a single forward observation exists for L9, and before any observation
exists for the whole basket (the ledger is empty at this freeze).** This fourth freeze does two
things and reconciles the record:

1. **Adds one genuinely new sized leg — L9 `CEFMUNIEQ`** (Y05 muni+equity CEF discount-LEVEL decile
   tilt, H=1 week), from `DEEPMINE_MASTER.md` §4, as a **SATELLITE (8%)** under a **combined CEF-class
   cap of 25%** (T12CEF + CEFMUNIEQ). Its own `spec_sha256` is verified by the logger.
2. **Demotes L7 `XS_GLSR_Z` from a sized leg (0.12) to UNSIZED / logging-only (0.0).** The perp
   cross-sectional positioning fade is now **logged but carries no basket weight**, joining L8
   (XS_SMART) as a zero-budget forward logger. Its universe and signal remain frozen exactly as in
   Appendix B; only its **sizing** changes, and its `spec_sha256` is re-computed to reflect the new
   status. This supersedes Appendix B's sizing of L7.

**Reconciliation note (the record was ahead of the task that ordered this freeze).** The instruction
that produced this freeze was written believing the frozen JSON held **six** legs and that a perp
leg had only been claimed (not added) in a memory note. In fact the **third freeze (Appendix B) had
already added L7 (XS_GLSR_Z, sized 0.12) and L8 (XS_SMART, unsized)** to the JSON, the `.md`, and the
logger. So of the two legs the instruction asked to "add", **XS_GLSR_Z already existed** in exactly
the requested deployable top-50 form — this freeze does not duplicate it, it **re-sizes it to zero**.
The second requested leg, the CEF muni satellite, is genuinely new and is added here as **L9** (the
task called it "L8"; slot L8 was already occupied by XS_SMART, so the CEF satellite takes the next
free slot L9 — the "L5 + L8 CEF cap" of the source spec is implemented as the **L5 + L9 (T12CEF +
CEFMUNIEQ) CEF-class cap**).

**Why L7 is now unsized (the sizing correction).** The deployable top-50 held-out net Sharpe is only
**+0.73** at the 5.5 bp/side rail and **−1.19** at the 15 bp/side cascade stress, on a **single**
held-out regime (2024-04..2025-01, 275 days) — the panel's Binance positioning feed thins after
2024-12, so there is no 2025-26 confirmation. Perp taker slippage has **never been measured** by this
programme; the 5.5 bp rail carries a 1.0 bp *declared, never-measured* half-spread, and breakeven is
only ~9 bp/side on the deployable universe. There is also a **live naming ambiguity**: the
authoritative `FORMULA_SWEEP_MASTER.md` names the promoted perp candidate **`XS_GLSR_Z`** (global
account long/short-ratio z-fade), while a later round-2 workflow output names **`X2_FLOWSTREAK`**
(24h taker-flow one-sidedness fade) with its own thin margin (held-out +2.31 @5.5bp but +0.54
@15bp, and a net **−0.67** intermediate window). The two disagree on which perp formula; the
conservative resolution — **carry the perp cross-sectional exposure at ZERO size until real perp
taker slippage is measured** — makes the disagreement moot for the combined book. We keep the
frozen `XS_GLSR_Z` spec (the one the authoritative document names and the one already frozen) and
log it unsized. **No perp formula carries basket weight at this freeze.**

Everything in §0 still governs: **this is a LOGGER. No orders, no real money, no position.** L9 reads
the same keyless CEFConnect GET already wired for L5 plus the frozen CEFConnect category statics and
Alpaca distribution-adjusted daily closes (read-only market-data host). Every held-out number quoted
below is a **selection-inflated UPPER BOUND**; the forward log is the only arbiter, and it is empty.

### The extended basket (v4)

| slot | id | family | horizon | status | budget | own sha256 |
|---|---|---|---|---|---|---|
| L1 | T3 | overnight X-sectional reversal | overnight | ACTIVE | 0.268 | — (v1) |
| L2 | ETFRV | identical-claim RV | intraday | ACTIVE | 0.214 | — (v1) |
| L3 | DUALCLASS | identical-claim RV | multi-day | ACTIVE | 0.139 | `fa67c73f…` |
| L4 | T7 | ex-dividend overnight event | overnight | ACTIVE | 0.075 | `e12cb470…` |
| L5 | T12CEF | CEF discount convergence (H=4) | 4-week | ACTIVE | 0.170 | `c60ceb57…` |
| L6 | ORB | intraday directional (probe) | intraday | ACTIVE | 0.054 | `b875c2fc…` |
| L7 | XS_GLSR_Z | crypto-perp X-sectional positioning | 24h | **ACTIVE_UNSIZED** | **0.00** | re-frozen (v4) |
| L8 | XS_SMART | crypto-perp X-sectional positioning | 24h | ACTIVE_UNSIZED | 0.00 | `28bb4edc…` |
| L9 | **CEFMUNIEQ** | **CEF discount convergence (muni+equity, H=1)** | **1-week** | **ACTIVE** | **0.08** | re-frozen (v4) |

**Risk budgets (`risk_budgets_active_v8`, sum = 1.0):** overnight (T3+T7) 0.343 : identical-claim RV
(ETFRV+DUALCLASS) 0.353 : **CEF class (T12CEF+CEFMUNIEQ) 0.25 (at the hard cap)** : ORB probe 0.054 :
perp (XS_GLSR_Z+XS_SMART) **0.00**. The CEF-class cap FORCES T12CEF's *deployed* budget down from
0.27 to 0.17 so the class does not exceed a quarter of the book (T12CEF's own leg-spec fraction 0.30
is unchanged — only the deployment dict moves). The combined `declared_trials_now` rises **7 → 8**
(CEFMUNIEQ is a new stood-up leg; killed/retired/unsized legs keep counting forever). The T13 vol
overlay, the T-bill benchmark, and the per-leg kill switch (N_min=40, drop at upper-95% < 0) apply
to all sized legs; the two unsized perp loggers accrue kill-switch streams but never touch the
combined book.

---

## L9 — CEFMUNIEQ muni+equity CEF discount-LEVEL tilt (Y05, H=1, SATELLITE) · re-frozen (v4)

- **Universe:** the keyless **CEFConnect `/api/v3/DailyPricing`** snapshot (reuses the L5 fetch),
  restricted to **Morningstar category MUNI or EQUITY only** (`CategoryName` from the frozen
  `research/data/t12_cache/universe.json.gz` statics). **TAXABLE-CREDIT CEFs are EXCLUDED** — in a
  credit CEF the discount is a yield-spread instrument, not a NAV-convergence instrument, so the tilt
  does not belong there. This is the **signal-defining choice**, not a filter. Price > $5 both legs;
  short leg restricted to Alpaca `easy_to_borrow=true` (HTB is a hard exclusion, never a price).
  Typical book 18 long / 8 short.
- **Signal:** `Discount = (Price − NAV)/NAV`; score = **`−Discount`** — the raw cross-sectional
  **LEVEL**, deliberately not a z-score, not a change, not an acceleration (every z/change/accel
  branch of this family is closing-print bid-ask bounce). Long the **widest-discount decile**, short
  the **narrowest/premium decile** of the restricted universe, dollar-neutral equal-weight. **Hold 1
  week, rebalance weekly** (realised turnover ≈ 0.33 of book/week). One weekly rebalance's realised
  net return = one settled observation.
- **Execution — MANDATORY 1 trading-day implementation lag.** CEFConnect publishes NAV *after* the
  close (`NAVPublished` trails `LastUpdated` by a session), so a discount observed on grid date *k*
  is actionable **no earlier than the next session's close**. Without the lag the book trades a price
  it could not have seen — the single correction that turns this family's headline Sharpe-5 formulas
  negative. Entry/exit at the closing print, weekly; **P&L on Alpaca `adjustment=all`
  distribution-adjusted closes** (CEFs pay 7–8%/yr; a raw-price series misstates the long leg).
- **Cost + borrow guard (both legs charged):** half-spread **p90 = 27.25 bp** (NOT the 11.53 bp
  median — the book deliberately holds the extremes of a universe whose spread is 11.5/18.4/27.2 at
  median/p75/p90) on realised turnover both sides; SEC §31 **0.278 bp** of sale notional; borrow at
  the **realised 200 bp/yr** short rate (not the 33 bp ETB floor), on the ETB-screened short.
- **MANDATORY GUARDS (sizing):** **SATELLITE, 8%** of basket risk (stressed alpha clears its
  pre-registered bar by only 1.06× and *fails* the conservative 66-alpha bar at 0.94×; it was a
  secondary pick whose pre-committed primary failed). **Combined CEF cap: L5 (T12CEF) + L9
  (CEFMUNIEQ) ≤ 25% of basket risk** — uncorrelated in returns (held-out corr −0.10) but adjacent in
  structure (same CEFConnect NAV pipeline, closing-auction regime, ~360-fund live-only universe, ETB
  list; design-window corr was +0.585 and could revert). **Hard notional cap** — the short leg is ~7
  names and CEF closing auctions clear $0.0–0.3 M; size to the auction, not the Sharpe. **26-week
  half-sample re-check** — the stressed held-out edge is entirely in one half (first 57 wk Sharpe
  0.54, second 57 wk Sharpe 3.53; 37% of the stressed mean is the 5 best of 114 weeks); no budget
  increase before the re-check under any forward result. Vol overlay: inherits the basket's
  `T13-VOL-L60-T0.1-WMAX1.0`.
- **Prior (upper bound):** design (2021-08..2024-02, 125 wk) net **t 4.98, ann Sharpe 3.213**
  (+28.95 bp/wk @11.53); held out (2024-03..2026-08, 114 wk) **+33.26 bp/wk NET, Sharpe 3.07, t 4.54**
  @11.53; **honestly stressed** (1-day lag + p90 27.25 bp both legs + 200 bp/yr borrow) **+18.58
  bp/wk, ann Sharpe 1.95, t 2.89**; stressed 2-factor alpha to L5 **t 2.93** vs the 2.751 second-round
  bar (1.06×; fails the conservative 66-alpha bar 3.125 at 0.94×); held-out corr/beta to L5
  −0.10/−0.003. Declared trials in the CEF family: **66**. Selection-inflated upper bound; the forward
  log is the arbiter.

---

*Fourth freeze appended 2026-08-20. Frozen instrument. No orders, no real money, no purchases, no
commit by the logger; free/cached data plus one keyless CEFConnect GET and read-only Alpaca
market-data only. The perp cross-sectional exposure (L7/L8) is logged UNSIZED until real perp taker
slippage is measured. Every backtested number herein is a selection-inflated upper bound; the forward
log is the only evidence, and it is empty.*


---

---

# APPENDIX D — FIFTH FREEZE (v5), 2026-08-20: L9 CEFMUNIEQ DE-SIZED to logging-only; sized legs renormalized; lag-aware session selection

**Frozen 2026-08-20, before a single forward observation exists (the ledger is empty at this
freeze).** This fifth freeze makes the logger honest on FREE data and removes a risk-budget mistake.
It changes **no leg's frozen SIGNAL or execution spec** — only (1) L9's *sizing/status* and its DSR
trial accounting, (2) the deployed risk-budget dict, and (3) the logger's *session-selection* logic
(a data-availability fix, not a rule change). The L1–L6 and L8 spec objects are **byte-identical** to
the earlier freezes and their `spec_sha256` values are **unchanged**; L7 (XS_GLSR_Z) stays UNSIZED as
frozen in v4. Only L9's `spec_sha256` is recomputed, exactly as L7's was when it was demoted in v4.

### 1. L9 (CEFMUNIEQ) DE-SIZED from the 0.08 satellite to UNSIZED / logging-only (0.0)

Per `DEEPMINE_MASTER.md`, Y05/CEFMUNIEQ's honestly-stressed 2-factor alpha to L5 is **t 2.93**, which
is only **0.94×** of the conservative multiple-testing bar **√(2 ln 132) = 3.125** (132 = the DEEPMINE
CEF-family formula count that sets the conservative bar). It clears only the *looser* 2.751
second-round bar (1.06×). **A leg that fails the conservative multiple-testing bar carries no risk
budget.** It is also **structurally adjacent to L5 T12CEF** — the same CEFConnect NAV pipeline,
closing-auction regime, ~360-fund live-only universe and ETB list (design-window return correlation
**+0.585**, which could revert from the −0.10 held-out figure) — so it adds little independent
diversification even if the edge is real. Both facts point the same way: **zero allocation.**

L9 is therefore set **`status = ACTIVE_UNSIZED`, budget 0.0**, joining L7 and L8 as a zero-budget
forward logger. It **still logs forward and accrues its per-leg kill-switch stream** — it simply
carries no weight and **never touches the combined book**. Its `declared_trials_in_leg_family` is
corrected **66 → 132** (the honest count behind the 3.125 bar), which raises its own DSR hurdle. This
is a *sizing + accounting* change: L9's `universe`, `signal`, `execution` and `cost_bp` blocks are
unchanged, so this is exactly the kind of re-freeze v4 applied to L7.

### 2. The remaining SIZED legs renormalized to sum to 1.0 (`risk_budgets_active_v9`)

Removing L9's 0.08 leaves the six sized legs (L1 T3, L2 ETFRV, L3 DUALCLASS, L4 T7, L5 T12CEF, L6 ORB)
summing to 0.92 in v8. Each is scaled by the **same** factor (1/0.92 ≈ 1.087), so **relative weights
and the three-independent-sources-plus-ORB-probe structure are preserved exactly**:

> overnight (T3 0.291304 + T7 0.081522) = **0.373** · identical-claim RV (ETFRV 0.232609 +
> DUALCLASS 0.151087) = **0.384** · CEF (T12CEF 0.184783) = **0.185** · ORB probe **0.058695**;
> CEFMUNIEQ = XS_GLSR_Z = XS_SMART = **0.00**. Sum = 1.0.

The combined CEF class is now T12CEF alone at 0.185, comfortably under the 0.25 cap (which is now
moot but retained). `risk_budgets_active_v9` supersedes v8 for the combined book; v8 and earlier are
retained for the record.

### 3. Lag-aware session selection (a data-availability fix, not a rule change)

The free Alpaca tier will not serve the **current day's** (and, for a session or two, recent) SIP /
auction data: a query returns **HTTP 403 "subscription does not permit querying recent SIP data"**.
"Log today" is therefore the wrong target. The logger now finds the **free-data horizon
empirically** — it walks back one session at a time and probes the auction endpoint, treating the 403
as "still embargoed" — and logs the **latest post-freeze, not-yet-logged session whose full
settlement data the free tier actually serves.** If none is available yet it **refuses gracefully**
(no crash, no phantom row) and writes nothing. Settlement cadence is respected by construction:
same-session legs (L2, L6) need the logged session's intraday+close; overnight legs (L1, L4) record
on the exit session's row, gated by that session's open auction plus the prior-run queued signal;
weekly/multi-day legs (L5, L9, L3) advance their state machines per session. **The as-of / lookahead
assertions and the no-pre-freeze-row guard are untouched.** Because the freeze date is 2026-08-20 and
the session spine excludes today, the freeze-day session becomes loggable only once it is a complete
past session *and* its data clears the embargo (~1–2 days); logging nothing on 2026-08-20 itself is
correct, and 2026-08-20 will be picked up automatically as soon as its data is free.

### The basket at v5

| slot | id | family | status | budget (v9) | own sha256 |
|---|---|---|---|---|---|
| L1 | T3 | overnight X-sectional reversal | ACTIVE | 0.291304 | — (v1) |
| L2 | ETFRV | identical-claim RV | ACTIVE | 0.232609 | — (v1) |
| L3 | DUALCLASS | identical-claim RV | ACTIVE | 0.151087 | `fa67c73f…` (unchanged) |
| L4 | T7 | ex-dividend overnight event | ACTIVE | 0.081522 | `e12cb470…` (unchanged) |
| L5 | T12CEF | CEF discount convergence (H=4) | ACTIVE | 0.184783 | `c60ceb57…` (unchanged) |
| L6 | ORB | intraday directional (probe) | ACTIVE | 0.058695 | `b875c2fc…` (unchanged) |
| L7 | XS_GLSR_Z | crypto-perp X-sectional positioning | ACTIVE_UNSIZED | 0.00 | `0df494cf…` (unchanged) |
| L8 | XS_SMART | crypto-perp X-sectional positioning | ACTIVE_UNSIZED | 0.00 | `28bb4edc…` (unchanged) |
| L9 | CEFMUNIEQ | CEF discount convergence (muni+equity, H=1) | **ACTIVE_UNSIZED** | **0.00** | re-frozen (v5) |

The combined `declared_trials_now` stays **8** (every leg ever stood up keeps counting; demotion does
not remove it). The T13 vol overlay, the T-bill benchmark and the per-leg kill switch (N_min = 40,
drop at upper-95 % < 0) apply to all six sized legs; the three unsized loggers (L7, L8, L9) accrue
kill-switch streams but never touch the combined book. `preregistration_sha256` is re-pinned to this
extended `.md`.

*Fifth freeze appended 2026-08-20. Frozen instrument. No orders, no real money, no purchases, no
commit by the logger; free/cached data plus one keyless CEFConnect GET and read-only Alpaca
market-data only. Every backtested number herein is a selection-inflated upper bound; the forward log
is the only evidence, and it is empty.*


---

---

# APPENDIX E — SIXTH FREEZE (v6), 2026-08-21: the risk budgets are DE-FIT to zero-parameter equal-risk

**Frozen 2026-08-21, before a single forward observation exists (the ledger is still empty at this
freeze).** This sixth freeze changes **exactly one thing: the deployed risk-budget dict.** It is a
**RISK-BUDGET change ONLY.** No leg's universe, signal, execution rail, cost model, guard, kill
switch, minimum sample, the T13 vol overlay, or the T-bill benchmark is touched. **Every leg's frozen
spec — and therefore every per-leg `spec_sha256` — is byte-identical to v5** (`DUALCLASS fa67c73f…`,
`T7 e12cb470…`, `T12CEF c60ceb57…`, `ORB b875c2fc…`, `XS_GLSR_Z 0df494cf…`, `XS_SMART 28bb4edc…`,
`CEFMUNIEQ 7af4baa2…`; L1/L2 carry no per-leg hash and are unchanged). The combined
`declared_trials_now` **stays 8** — this is a *de-fit*, not a new trial or a new leg.

### Why: round 3 proved that FITTING the budgets overfits

`INVENT_R3_MASTER.md` §4 P1 (`ENS_EQRISK_ALL3`) measured the currently-frozen fitted budgets against
the un-fitted a-priori default on a 188-week held-out window: **the fitted v5 budgets travelled at
held-out Sharpe 2.45 versus 2.93 for doing nothing — a cost of −0.48 Sharpe out of sample.** The
textbook overfit signature was replicated across the whole weighting family: *the more the weights
are allowed to learn, the worse they travel* (`ENS_MINVAR` 2.93, `ENS_SHARPE_WEIGHTED` 2.90, four
regime-switching fitted weightings 2.59–2.97, all at or below the parameter-free default). Choosing
the simpler of two already-deployed weightings is **not** a multiple-testing event — there is nothing
to select between, the default has no parameters, and the evidence is a *negative* result about the
fitted alternative. **While the ledger is empty is the only honest moment to make this switch** (a
budget change after observations exist would be a search on a forward outcome, forbidden by §7c).

### What the new budgets are (`risk_budgets_active_v10`)

The target is **equal-RISK-contribution**: for the six SIZED legs (L1 T3, L2 ETFRV, L3 DUALCLASS,
L4 T7, L5 T12CEF, L6 ORB), `weight_i ∝ 1/(design vol of leg i)`, normalized to sum to 1.0, so each
leg contributes equal risk to the combined book. The three logging-only legs (L7 XS_GLSR_Z, L8
XS_SMART, L9 CEFMUNIEQ) stay at **0.0 / ACTIVE_UNSIZED**, exactly as v5.

**The stated fallback is taken, and here is the honest reason.** One of the six sized legs — **L2
ETFRV** — carries **no usable design volatility**: its frozen `prior_verdict` is "Not run OOS …
expected net 1.0–1.5 bp, market-neutral," with no Sharpe, no t, no n, no dispersion, and there is no
wired cached design series (unlike L3/L5/L6/L4, ETFRV has no `*_proof` engine) from which one could
be computed. Imputing a volatility for it would be exactly the hand-tuning this de-fit exists to
remove. Moreover, the five legs that *do* carry a computable per-observation design vol settle on
**wildly different native cadences** (T3 per night, T7 per event-day, T12CEF per 4-week tranche,
DUALCLASS per round-trip, ORB per session), so a defensible inverse-vol weighting would additionally
require normalizing every leg onto one common calendar — an analyst judgment the `ENS_EQRISK_ALL3`
test performed on its three legs ("each scaled to unit design vol on a weekly calendar") but which
cannot be done here without hand-picking a calendar-conversion for each heterogeneous leg. Both facts
point the same way, and the pre-registered contingency is explicit: **when a sized leg has no usable
design vol, fall back to equal-DOLLAR — 1/6 each.** That is what is deployed:

> T3 = ETFRV = DUALCLASS = T7 = T12CEF = ORB = **1/6 ≈ 0.166667** (sum = 1.0);
> CEFMUNIEQ = XS_GLSR_Z = XS_SMART = **0.00**.

Equal-dollar 1/6 is the **simplest possible zero-parameter default** — even simpler than inverse-vol
— and it fully honors the round-3 finding, which is a negative result about *fitting*, not a positive
discovery about inverse-vol specifically. The combined CEF class is now T12CEF alone at 0.167, still
under the retained 0.25 CEF-class cap. For the record, the per-observation design volatilities that
*were* computable from the frozen priors (and would drive an inverse-vol scheme if ETFRV had one and
a common calendar were fixed) are: **T3 ≈ 66 bp/night** (from OOS Sharpe 1.21), **T7 ≈ 36 bp/event-day**
(t 2.96, n 1018), **DUALCLASS ≈ 124 bp/round-trip** (ETB t 1.31, n 165), **T12CEF ≈ 41 bp/week**
(t 3.51, n 116), **ORB ≈ 155 bp/day** (ann Sharpe 0.494); **ETFRV = none.** These are recorded, not
deployed.

### What changes in the logger

`risk_budgets_active_v10` is published and the combined book reads it as the active dict (the logger's
budget-selection chain now prefers v10, falling back to v9…v6 for older ledger rows). The selftest's
budget assertions now enforce the **equal-risk scheme** — the six sized legs carry *equal* budgets
summing to 1.0, all three unsized loggers carry zero, and the CEF class stays under its cap — in place
of the old v5 assertion (which hard-enforced the fitted uniform 1/0.92 renormalization and the forced
0.25 CEF-cap deployment). The lookahead / as-of assertions, the no-pre-freeze-row guard, the per-leg
`spec_sha256` verification, and the kill switch are all untouched. `preregistration_sha256` is
re-pinned to this extended `.md` (the v5 hash is preserved as `preregistration_sha256_v5`).

*Sixth freeze appended 2026-08-21. Frozen instrument. No orders, no real money, no purchases, no
commit by the logger; free/cached data plus one keyless CEFConnect GET and read-only Alpaca
market-data only. A risk-budget de-fit only — no leg spec changed, every per-leg hash unchanged.
Every backtested number herein is a selection-inflated upper bound; the forward log is the only
evidence, and it is empty.*


---

---

# APPENDIX F — SEVENTH FREEZE (v7), 2026-08-21: two ADDITIVE UNSIZED band-variant loggers + the ρ1 gate

**Frozen 2026-08-21, before a single forward observation exists (the ledger is empty at this
freeze).** This seventh freeze is **purely ADDITIVE and LOGGING-ONLY**. It changes **no sized leg's
spec, no band, no risk budget, and no existing `spec_sha256`.** It does three things:

1. **Adds two new `ACTIVE_UNSIZED` (risk budget 0.0) band-variant loggers**, each with its OWN
   `spec_sha256`, mirroring the L7–L9 unsized pattern:
   - **L10 `ETFRV_Z20`** — identical to the SIZED **L2 ETFRV** leg in every way (same 5 pairs, same
     15:45→close execution rail, same per-symbol cost model, same distribution screen) **EXCEPT the
     entry band is `|z| ≥ 2.0`** (the OU-recommended wider band). `spec_sha256 4b4a1229…`
   - **L11 `DUALCLASS_EXIT10`** — identical to the SIZED **L3 DUALCLASS** leg (same 16-pair universe,
     `K_entry = 2.0`, `L = 250`, `max_hold = 20`, per-symbol cost model, and the MANDATORY
     easy-to-borrow short-leg guard + frozen ETB whitelist) **EXCEPT the exit band is widened to
     `|z| ≈ 1.0`** (the OU-recommended wider exit). `spec_sha256 54e199ac…`

2. **Adds the standing ρ1(Δs) measurement-error gate** to the pre-registration (§7d above) as a
   binding rule on any FUTURE relative-value leg.

3. **Re-pins `preregistration_sha256`** to this extended `.md` (the v6 hash is preserved as
   `preregistration_sha256_v6`).

**WHY (the rigor).** `OU_MEAN_REVERSION.md` found the frozen L2 `|z| ≥ 1.5` band is
bounce-dominated (`ρ1(Δs) ≈ −0.5`) and **net-NEGATIVE out of sample** (−0.13 bp/session, t −1.78,
Sharpe −1.62), while `|z| ≥ 2.0` is the first net-positive band OOS (+0.09 bp, t +0.74, Sharpe
+0.92); and that widening L3's exit from 0.5 to ≈1.0 lifts held-out book Sharpe 0.50 → 0.66 on more
trades. **But both bands were CHOSEN on the held-out window**, so retroactively re-freezing the SIZED
L2/L3 legs to them would be in-sample selection (overfitting). The disciplined move is to log the
variants **UNSIZED in parallel** and let a genuinely-forward test — not a spent backtest — adjudicate
whether the OU-derived bands actually beat the frozen ones. **Neither variant is ever allocated**;
each is kill-switched forward exactly like L7–L9 and never touches the combined book.

### The basket at v7 (6 SIZED + 5 UNSIZED loggers)

| slot | id | family | status | budget | own sha256 |
|---|---|---|---|---|---|
| L1 | T3 | overnight X-sectional reversal | ACTIVE | 1/6 | — (v1) |
| L2 | ETFRV | identical-claim RV | ACTIVE | 1/6 | — (v1) |
| L3 | DUALCLASS | identical-claim RV | ACTIVE | 1/6 | `fa67c73f…` (unchanged) |
| L4 | T7 | ex-dividend overnight event | ACTIVE | 1/6 | `e12cb470…` (unchanged) |
| L5 | T12CEF | CEF discount convergence (H=4) | ACTIVE | 1/6 | `c60ceb57…` (unchanged) |
| L6 | ORB | intraday directional (probe) | ACTIVE | 1/6 | `b875c2fc…` (unchanged) |
| L7 | XS_GLSR_Z | crypto-perp X-sectional positioning | ACTIVE_UNSIZED | 0.00 | `0df494cf…` (unchanged) |
| L8 | XS_SMART | crypto-perp X-sectional positioning | ACTIVE_UNSIZED | 0.00 | `28bb4edc…` (unchanged) |
| L9 | CEFMUNIEQ | CEF discount convergence (muni+equity, H=1) | ACTIVE_UNSIZED | 0.00 | `7af4baa2…` (unchanged) |
| **L10** | **ETFRV_Z20** | **identical-claim RV — |z|≥2.0 band variant** | **ACTIVE_UNSIZED** | **0.00** | `4b4a1229…` |
| **L11** | **DUALCLASS_EXIT10** | **identical-claim RV — exit |z|≈1.0 band variant** | **ACTIVE_UNSIZED** | **0.00** | `54e199ac…` |

**Budgets unchanged.** `risk_budgets_active_v10` (the deployed dict the combined book reads) is
byte-unchanged: the six SIZED legs each carry **1/6**, summing to 1.0; L10/L11 join L7/L8/L9 at
**ZERO** and are excluded from the combined book by construction (never added to `contributions`).
**No new data or fetch:** L10 shares L2's already-computed fired-pair book (its fired set is the
subset clearing `|z| ≥ 2.0`, so re-filtering by `|z|` is exact); L11 shares L3's daily-bar series.

**Declared-trials accounting (honest).** `combined_gate.declared_trials_now` **stays 8**. Exactly as
the XS_SMART sibling of L7 ("the same hypothesis … logged but not separately counted"), L10 and L11
are the SAME hypotheses as L2 and L3 at a different band — logged and kill-switched forward, but not
separately added to the combined trial count. Each carries its own per-leg
`declared_trials_in_leg_family` (5 for the OU entry-band grid; 18 for the dual-class family) for its
own DSR.

**Ledger.** Because v7 is a new freeze version, a new ledger begins under it — the code's own
contract (`load_state` refuses a state written under a different freeze hash and directs "start a new
ledger under a new freeze"). The archived v6 ledger held one session row with **zero settled
observations** (inception `None`, curves 1.0), so **no evidence is lost**. Ledger empty at this
freeze — freeze precedes observation.

*Seventh freeze appended 2026-08-21. Frozen instrument. No orders, no real money, no purchases, no
commit by the logger; free/cached data plus one keyless CEFConnect GET and read-only Alpaca
market-data only. ADDITIVE unsized band variants + the ρ1 gate — no sized leg spec/band/budget
changed, every existing per-leg hash unchanged. Every backtested number herein is a
selection-inflated upper bound; the forward log is the only evidence, and it is empty.*


---

---

# APPENDIX G — EIGHTH FREEZE (v8), 2026-08-22: L12 CRYPTO_LOWVOL added (UNSIZED) + two standing method rules

**Frozen 2026-08-22, before a single forward observation exists for L12 (the ledger is empty at this
freeze).** This eighth freeze is **purely ADDITIVE and LOGGING-ONLY**. It changes **no sized leg's
spec, no band, no risk budget, and no existing `spec_sha256`.** It does three things:

1. **Adds one new `ACTIVE_UNSIZED` (risk budget 0.0) logging leg**, with its OWN `spec_sha256`,
   mirroring the L7–L11 unsized pattern:
   - **L12 `CRYPTO_LOWVOL`** — cross-sectional realised-volatility on Binance spot USDT top-50
     (`INVENT_0822B_MASTER.md` §2.1, `S1_VOL30|H20`). `spec_sha256 08f7e5a1…`

2. **Adds the two standing methodology rules** of §7e above (the broken rotate-the-returns placebo,
   and the ρ1-mirror fake-momentum gate) as binding rules on all FUTURE work.

3. **Re-pins `preregistration_sha256`** to this extended `.md` (the v7 hash is preserved as
   `preregistration_sha256_v7`).

**WHY UNSIZED (the honest gate).** The factor is real on every stated test — but it is **not sizable
on free data** and it is **not an invention**. Three facts hold it at zero:

- **The premium is ENTIRELY the short leg, and the short leg is borrow-walled.** Held-out leg
  decomposition: long low-vol **+5.8%/yr**, short high-vol **+60.3%/yr** — the short high-vol sleeve
  is **91% of gross P&L** (well above the 70% floor). High-volatility alts bleed and this book
  harvests that bleed; the long leg is a financing leg. **No free feed prices the Binance spot alt
  borrow**, and the frozen net Sharpe is quoted **before any borrow** — this is exactly lesson 7.
- **Capacity is low single-digit $M** (20 names at a \$1 M ADV floor; the edge halves at a \$100 M
  floor).
- **Its P&L overlap with L7 `XS_GLSR_Z`** — the perp positioning fade over the **same** alt universe
  on the **same** exchange — is **unmeasured.** "Diversifying" is established against the US-equity
  sleeve (zero instrument overlap) and **unmeasured against the crypto sleeve.**
- **It is a FOUND PUBLISHED FACTOR** (the crypto low-volatility / lottery-MAX anomaly), sitting
  against the standing "invent, don't replicate" instruction, and its held-out window (2023-01 …
  2026-08) has already been read by D0821 crypto-spot and by rounds 2/3 on perps. Logged, not sized.

### L12 — CRYPTO_LOWVOL cross-sectional realised-vol (NEW unsized logger) · `spec_sha256 08f7e5a1…`

- **Universe:** point-in-time **TOP-50** Binance spot USDT names by trailing-**30d** dollar ADV
  (quote volume) through day *t−1*, ≥ **\$1 M** ADV floor, **stablecoins / wrapped / staked / gold
  tokens excluded** by base symbol (the frozen `STABLE_BASES` set), VWAP required inside the day's
  `[low,high]` range and present on entry *t* and mark *t+1*. Point-in-time, no survivorship.
- **Signal:** `S1_VOL30` = **30-day trailing realised volatility of daily VWAP log-returns**
  (VWAP = quote_volume / base_volume), causal — uses data **through the close of day *t−1***. Rank the
  ~50-name cross-section by 30d vol; **LONG the 10 LOWEST-vol, SHORT the 10 HIGHEST-vol** (`sign = −1`),
  equal-weight, dollar-neutral, unit gross. **20-day hold** as **20 overlapping daily tranches**
  (turnover ≈ 0.047/day).
- **Execution:** signal through close *t−1*; **entry at the VWAP of day *t*, mark to the VWAP of day
  *t+1*** — signal and P&L are **two lags apart**, neutralising the VWAP-mirror artefact (§7e rule 2).
  Cost **10 bp/side** on realised turnover. The frozen inv0822b crypto-XS engine
  (`inv0822b_xs_lib` + `inv0822b_xs_forms.S1_VOL30`) is reused verbatim, driven by the frozen leg
  fields; nothing re-typed. **The LONG (low-vol) and SHORT (high-vol) sleeves are logged SEPARATELY**
  so the gate-4 short-leg-fraction kill switch is computable forward.
- **Data / no new fetch:** reads **only** the already-cached frozen spot panel
  `research/data/xspot_cache/spot_daily.npz` (cached through 2026-08-20; built by the inv0822b
  crypto-spot fetch) — **no crypto venue, no key, no order, no new fetch**, exactly as L7/L8 read the
  frozen perp panel. The `proof` reproduces the held-out number from this cache; the **forward step
  records a data-availability gate** (the research snapshot ends in the past; forward settlement is
  **pending a maintained panel extension — a DETACHED background fetch, never inline**) and
  **contributes NOTHING**. No phantom mark is fabricated.

- **THE FOUR PRE-SIZING GATES (verbatim, all four required before any sizing):**
  1. **Borrow gate.** A collected Binance spot alt **borrow-rate AND borrow-limit curve**. The trade
     does not die on any plausible number (held-out net **2.45** at 5 bp/day, **2.04** at 10 bp/day,
     **1.24** at 20 bp/day; **1.52** at a \$25 M ADV floor + 10 bp/day) — it dies on **not having the
     number.** Exactly lesson 7.
  2. **Capacity gate.** 20 names at a \$1 M ADV floor; the edge **halves at a \$100 M floor.** Low
     single-digit \$M. Any size beyond that is untested.
  3. **Overlap gate.** Measure **P&L correlation to L7 `XS_GLSR_Z`** before it shares risk budget with
     it. **Unmeasured** at this freeze.
  4. **Kill switch (long/short split).** The premium is **one leg.** Log the LONG and SHORT sleeves
     **separately** from day one; if the **short sleeve's contribution falls below ~70% of gross**
     over a rolling quarter, the thing being collected is **not** what was frozen. Held-out short-leg
     gross fraction **0.91**.

- **Prior (UPPER BOUND):** design (2019-01 … 2023-01) net **+1.95 (t 3.91)**; **held out
  (2023-01-01 … 2026-08-01, sign FROZEN to `_cryptoXS_DESIGN.json` before the window opened) net
  Sharpe +2.85 (t 5.39)** at 10 bp/side, **+2.77 at a 20 bp shock**; 64.5%/yr on 22.6% vol,
  break-even **390 bp/side**; positive in every calendar year 2019-2026, **69/92 months**, min
  rolling-1y net SR +0.08, skew +0.02. Cleared the theme slot-permutation placebo (0 of 400
  replicates reach the observed), the theme analytic bar and the programme-cumulative bar; pooled over
  the round its **design** t 4.04–4.28 sits at the pooled p99 (marginal), and the **held-out** t 5.39
  is what carries it. Declared trials in its own family: **177** (the round's pre-registered formula
  count). **Found published factor, not an invention. Selection-inflated upper bound; the forward log
  is the arbiter.**

### The basket at v8 (6 SIZED + 6 UNSIZED loggers)

| slot | id | family | status | budget | own sha256 |
|---|---|---|---|---|---|
| L1 | T3 | overnight X-sectional reversal | ACTIVE | 1/6 | — (v1) |
| L2 | ETFRV | identical-claim RV | ACTIVE | 1/6 | — (v1) |
| L3 | DUALCLASS | identical-claim RV | ACTIVE | 1/6 | `fa67c73f…` (unchanged) |
| L4 | T7 | ex-dividend overnight event | ACTIVE | 1/6 | `e12cb470…` (unchanged) |
| L5 | T12CEF | CEF discount convergence (H=4) | ACTIVE | 1/6 | `c60ceb57…` (unchanged) |
| L6 | ORB | intraday directional (probe) | ACTIVE | 1/6 | `b875c2fc…` (unchanged) |
| L7 | XS_GLSR_Z | crypto-perp X-sectional positioning | ACTIVE_UNSIZED | 0.00 | `0df494cf…` (unchanged) |
| L8 | XS_SMART | crypto-perp X-sectional positioning | ACTIVE_UNSIZED | 0.00 | `28bb4edc…` (unchanged) |
| L9 | CEFMUNIEQ | CEF discount convergence (muni+equity, H=1) | ACTIVE_UNSIZED | 0.00 | `7af4baa2…` (unchanged) |
| L10 | ETFRV_Z20 | identical-claim RV — \|z\|≥2.0 band variant | ACTIVE_UNSIZED | 0.00 | `4b4a1229…` (unchanged) |
| L11 | DUALCLASS_EXIT10 | identical-claim RV — exit \|z\|≈1.0 band variant | ACTIVE_UNSIZED | 0.00 | `54e199ac…` (unchanged) |
| **L12** | **CRYPTO_LOWVOL** | **crypto-spot X-sectional realised-vol (S1_VOL30\|H20)** | **ACTIVE_UNSIZED** | **0.00** | `08f7e5a1…` |

**Budgets unchanged.** `risk_budgets_active_v10` (the deployed dict the combined book reads) is
byte-unchanged: the six SIZED legs each carry **1/6**, summing to 1.0; L12 joins L7–L11 at **ZERO**
and is excluded from the combined book by construction (never added to `contributions`). **No new
data or fetch:** L12 reads only the already-cached frozen spot panel.

**Declared-trials accounting (honest).** `combined_gate.declared_trials_now` **stays 8** — L12 is a
new hypothesis but is **UNSIZED / logging-only** and carries no combined-book weight, so it is not
added to the combined trial count (exactly as the XS_SMART sibling of L7 and the L10/L11 band
variants). L12 carries its own per-leg `declared_trials_in_leg_family = 177` (the round's
pre-registered formula count) for its own DSR.

**Ledger.** Because v8 is a new freeze version, a new ledger begins under it — the code's own contract
(`load_state` refuses a state written under a different freeze hash). Ledger empty at this freeze —
freeze precedes observation.

*Eighth freeze appended 2026-08-22. Frozen instrument. No orders, no real money, no purchases, no
commit by the logger; free/cached data plus one keyless CEFConnect GET and read-only Alpaca
market-data only (L12 adds one read-only local cache — the frozen Binance spot panel — no crypto
venue, no key, no new fetch). ADDITIVE unsized leg + two standing method rules — no sized leg
spec/band/budget changed, every existing per-leg hash unchanged. Every backtested number herein is a
selection-inflated upper bound; the forward log is the only evidence, and it is empty.*


---

---

# APPENDIX H — NINTH FREEZE (v9), 2026-08-22: CORRECTIVE / SUBTRACTIVE re-freeze

**Frozen 2026-08-22, while the ledger is EMPTY (zero forward observations). That timing is the whole
point: every change here is a bug fix or a risk-reducing SUBTRACTION, made before real data accrues,
so it is costless now.** No new signal or leg is added. No orders, no real money, no position — this
remains a LOGGER. The five corrections below come from `research/trading_bot/INVENT_0822C_MASTER.md`
(the N1/E1/E2 escalations against the LIVE basket and the shared-cache dividend bug). Nothing here
is a search on a forward outcome; the ledger has none.

### The data bug that motivated the re-freeze

`research/data/t7_cache/corporate_actions_all.json.gz` carried **exactly-duplicated** records from an
overlapping paging window: **26,701 duplicate cash-dividend rows removed** (385,845 → 359,144;
26,005 exact-`id` duplicates + 696 same-`(symbol, ex_date, rate)` re-issues), **245 duplicate splits
removed** (forward 980 → 942, reverse 5,637 → 5,430), plus exact-`id` duplicates in every other
corporate-action list. Summing the raw records **doubled the published dividend on ~8% of ex-dates
and squared split factors** — a one-directional INFLATION. The cache was **deduplicated in place**
(original preserved at `corporate_actions_all.json.gz.corrupt.bak`); dedup key = `id` first, then
`(symbol, ex_date, rate)` for dividends and `(symbol, ex_date, old_rate, new_rate)` for splits, so
distinct rates on one ex-date (regular + special) are KEPT and summed. Every removed record was
verified byte-identical to a survivor.

### THE FIVE CORRECTIONS

1. **Dividend cache deduplicated (data fix).** As above. The bug only inflates, so every cell that
   DIED on it stays dead; only LIVE consumers needed re-checking, and the one that mattered is L4.

2. **L4 (T7 ex-open dividend residual) DE-SIZED to `ACTIVE_UNSIZED`.** Re-running L4's held-out
   number (2022–2026, n = 1018, frozen config) on the CLEAN cache with the exact
   `t7_d1_net_reassess` machinery: the corrupted panel reproduces the frozen prior VERBATIM (net
   **+3.347 bp/event-day, t 2.96**; net−control +3.263 bp, t 2.86; stress-h +0.487 bp). On the
   deduplicated dividends it **COLLAPSES**: net **+0.90 bp/event-day, t 0.81** (gross t 3.29 → 1.14,
   net−control +0.81 bp t 0.73, DSR@8 0.855 → 0.139), and it goes **negative (−1.96 bp, t −1.77) at a
   real half-spread rung**. Only **440 of 6,239 events (~7%)** changed rate, yet they carried the
   ENTIRE edge — the doubled-dividend inflation was fully load-bearing. L4 therefore fails "still
   positive, t meaningfully > 0 net of cost" and is DEMOTED to logging-only (risk budget 0.0). It
   keeps logging forward and accrues its kill-switch stream; it never touches the combined book. Its
   own `spec_sha256` is recomputed to reflect the new status (exactly as L7 was re-frozen when
   demoted in v4).

3. **L2 (ETF-sibling RV) DE-SIZED to `ACTIVE_UNSIZED`.** E1: all five pairs FAIL the ρ1 bounce gate
   (−0.503/−0.463/−0.457/−0.441/−0.491 vs the −0.35 bar). The frozen spec computes z from the 15:45
   print and **fills at that same 15:45 print** (R3 shared-price failure). Move the fill to 15:50:
   GROSS +1.295 bp (t 17.95) → **+0.076 bp (t 1.05)** — 94% of the gross edge gone in five minutes;
   NET +0.10 bp / SR 0.74 → **−1.12 bp / t −15.4 / SR −8.0**. A gross t of 17.95 against a 2.97 bar
   clears any multiple-testing correction by a mile and is still entirely fake — the sharpest
   available demonstration that the gross bar is necessary but not sufficient. L2's risk budget is set
   to **0.0**; it keeps logging and must be re-spec'd on a **15:50 fill** before any resize. Its
   unsized band-variant **L10 (ETFRV_Z20)** inherits the SAME shared-price defect and is marked
   **fake-until-respecced** in its guard (already 0.0 budget — no budget change).

4. **L3 (DUALCLASS) resized to the gap-1 honest number; BRK.A/BRK.B dropped.** E2: the one-day-gap
   re-entry test halves the headline — 50.09 bp (t 6.54) → **23.73 bp (t 3.59)** at gap 1 (19.97 bp
   at gap 2); half the 50.09 bp headline was same-close bounce. 15 of 16 pairs pass ρ1; **BRK.A/BRK.B
   fails at −0.459** and is **removed from the universe** (and from the cost table and ETB whitelist).
   L3 STAYS SIZED. Its honest forward expectation is recorded as **~23.73 bp/round-trip (gap-1 rung),
   NOT the 50.09 bp headline**, so the forward kill-switch judges it against the spec it actually has.
   Its L11 variant (DUALCLASS_EXIT10) gets the identical BRK removal. Both `spec_sha256` recomputed.

5. **T13 SPY vol-overlay REMOVED from the combined book.** N1: the overlay (`rule_id
   T13-VOL-L60-T0.1-WMAX1.0`) COSTS Sharpe on the dollar-neutral book in **every window on every
   panel** (dSharpe held-out −0.031 / −0.215 / −0.189, full-window −0.050 / −0.313 / −0.308). T13 was
   validated on a LONG-SPY book; the basket legs are dollar-neutral, so SPY vol is uninformative about
   them and `wmax=1.0` makes it a one-sided drag. The combined book is now **unlevered / un-overlaid**
   (effective `w_vol = 1.0`). Per N1's guard, the overlay weight is still COMPUTED and logged as a
   non-applied **reference** (`w_vol_overlay_reference`) so the forward record carries the book WITH
   and WITHOUT the overlay; only WITHOUT is deployed. The `vol_overlay` block is marked
   `removed_from_combined_book_v9`.

### Re-normalisation of the SIZED sleeve — zero-parameter equal weight

After demoting L2 and L4, **four SIZED legs remain: L1 T3, L3 DUALCLASS, L5 T12CEF, L6 ORB.** They are
re-normalised to **equal dollar weight, 1/4 = 0.25 each**, summing to 1.0 — the round-3 anti-fitting
lesson (fitting the budgets cost −0.48 Sharpe OOS; the ledger is empty, so this is the honest moment).
Published as `risk_budgets_active_v11` (the deployed dict the combined book now reads). The combined
CEF class = T12CEF alone = 0.25, exactly at the retained 0.25 cap. The five logging-only legs (L2
ETFRV, L4 T7, L7 XS_GLSR_Z, L8 XS_SMART, L9 CEFMUNIEQ) and the three band/factor loggers (L10, L11,
L12) all carry ZERO.

| slot | id | status (v9) | budget (v11) |
|---|---|---|---|
| L1 | T3 | ACTIVE (sized) | 0.25 |
| L3 | DUALCLASS | ACTIVE (sized, gap-1, no BRK) | 0.25 |
| L5 | T12CEF | ACTIVE (sized) | 0.25 |
| L6 | ORB | ACTIVE (sized) | 0.25 |
| L2 | ETFRV | **ACTIVE_UNSIZED** (demoted, 15:45 shared-price) | 0.00 |
| L4 | T7 | **ACTIVE_UNSIZED** (demoted, clean-cache collapse) | 0.00 |
| L7 | XS_GLSR_Z | ACTIVE_UNSIZED | 0.00 |
| L8 | XS_SMART | ACTIVE_UNSIZED | 0.00 |
| L9 | CEFMUNIEQ | ACTIVE_UNSIZED | 0.00 |
| L10 | ETFRV_Z20 | ACTIVE_UNSIZED (fake-until-respecced) | 0.00 |
| L11 | DUALCLASS_EXIT10 | ACTIVE_UNSIZED (no BRK) | 0.00 |
| L12 | CRYPTO_LOWVOL | ACTIVE_UNSIZED | 0.00 |

**Declared-trials accounting.** `combined_gate.declared_trials_now` **stays 8** — demoting or shrinking
a leg does NOT remove it from the count; killed/retired/demoted legs keep counting forever, so the DSR
bar does not shrink. Everything else — the per-leg kill switch (N_min=40, drop at upper-95% < 0), the
T-bill benchmark, the as-of/lookahead guards, the no-pre-freeze-row guard, `minimum_before_verdict` —
is untouched.

**Ledger.** Because v9 is a new freeze version, a new ledger begins under it (the code's contract: a
state written under a different freeze hash starts a new ledger). Ledger empty at this freeze — freeze
precedes observation.

*Ninth freeze appended 2026-08-22. CORRECTIVE / SUBTRACTIVE only. Frozen instrument. No orders, no
real money, no purchases, no commit by the logger; free/cached data only. No new signal or leg. Every
change is a bug fix (the dividend cache) or a risk-reducing subtraction (two de-sizings, one universe
removal, one overlay removal, one honest-expectation reset). `preregistration_sha256` re-pinned to
this extended .md (v8 hash preserved as `preregistration_sha256_v8`). Every backtested number herein
is a selection-inflated upper bound; the forward log is the only evidence, and it is empty.*


---

---

# APPENDIX I — TENTH FREEZE (v10), 2026-08-23: two UNSIZED options-flow challengers (L13, L14)

**Frozen 2026-08-23, while the ledger is still EMPTY (zero forward observations), the LAST additions
before the forward clock starts Monday. That timing is the whole point — logging-only legs added
before any datum are costless now.** This freeze is **ADDITIVE and LOGGING-ONLY**: it adds two new
`ACTIVE_UNSIZED` (risk budget **0.0**) legs, each with its **own `spec_sha256`**, mirroring the
L7–L12 unsized pattern. It changes **NO sized leg, NO risk budget, and NO existing `spec_sha256`**.
No orders, no real money, no position — this remains a LOGGER, reading only the frozen local
expired-OPRA options panel (`research/data/inv0823_gex/panel.json.gz`); no options venue, no key, no
order, no new fetch.

The two legs come from `research/trading_bot/INVENT_0823_gamma.md` (pre-registration
`INVENT_0823_gamma_PREREGISTRATION.md`, committed `a86abe1` before any backtest number existed; frozen
design table `e8dd7a0` before the held-out window was read) — the **single-name dealer-gamma /
options-flow** sweep, **the first non-noise theme result in six consecutive sweeps.**

### L13 — `SKEW_TILT` (S6, the strong invention survivor) · `spec_sha256 51b1d87e…`

- **Signal (S6_SKEW_TILT):** `S6 = ( Σ_{K>S} γ_K·callOI_K − Σ_{K<S} γ_K·putOI_K ) / Σ_all γ_K·OI_K`
  — gamma-weighted OTM call-OI minus OTM put-OI over total gamma-OI (Black–Scholes gamma weighting,
  OTM/ITM split, `/gross` normaliser), cross-sectionally rank-normalised **over the single-name
  cross-section**, dollar-neutral **long the top / short the bottom**, sign frozen from the design
  table.
- **Universe — SINGLE NAMES ONLY (34).** AAPL MSFT NVDA TSLA AMZN META GOOGL AMD NFLX AVGO JPM BAC XOM
  CVX WMT COST CRM INTC MU PLTR COIN BA DIS UBER PYPL GS PFE JNJ T VZ ORCL QCOM CAT LLY. **The 15
  sector/broad ETFs (XLF XLE XLK XLV XLI XLP XLU XLB XLRE XLC SMH IWM QQQ DIA EEM) are EXCLUDED** — the
  sector-ETF half is dead (held-out Sharpe **0.55**, net −0.01 at 3 bp), the survivor is a single-name
  effect (single-name-only held-out Sharpe **3.61**).
- **Rail:** signal from option bars through the **close of day t**, **enter at the OPEN of t+1**
  (≥17.5 h gap, never a shared print), **exit at the OPEN of t+2** (`day` horizon). Cost **3.0 bp/side**
  primary (1.0 / 3.0 / 5.5 grid), turnover measured. Reuses the frozen `invent0823_gex_eval` engine
  verbatim.
- **Prior (UPPER BOUND):** single-name-only held out (260 sessions, sign frozen) gross Sharpe **3.61**,
  gross 12.05 bp/day, t 3.66, **net Sharpe +3.06 at 3 bp/side**, one-day-gap placebo **+3.53**,
  break-even 19.9 bp/side; design (352 sessions) Sharpe 3.87, net@3 +3.25. (Full-universe held-out
  cross-checks the dossier exactly: gross 7.90 bp, Sharpe 3.58, t 3.64, net@3 +2.92, break-even 16.1.)

### L14 — `SKEW_TILT_CRUDE` (the pre-registered greeks-free competitor) · `spec_sha256 b3f61b8f…`

- **Signal:** `crude = (callVol − putVol)/(callVol + putVol)` — the day's call minus put traded
  contract **volume** over their sum, **no greeks, no moneyness split, no gamma weighting.** Same
  single-name universe, entry, exit and cost as L13.
- **Why it exists (`INVENT_0823_gamma.md` §5):** the entire Black–Scholes apparatus **adds nothing** —
  the crude volume imbalance does as well in design and **better** out of sample. So the real effect is
  an options **order-flow imbalance** predictor, **NOT a dealer-gamma effect.** In the dossier the
  crude variant was constructed **post-hoc** (after both windows were read) as a mechanism diagnostic;
  this is its **first pre-registered forward test.**
- **PROMOTION RULE (per the guard):** if the CRUDE book **matches or beats** S6 on the forward log, the
  **CRUDE is the promotion candidate** (simpler = less overfit).
- **Prior (UPPER BOUND):** single-name-only held out (260 sessions) gross Sharpe **4.47**, gross 14.0
  bp/day, t 4.54, **net Sharpe +4.33 at 3 bp/side**, one-day-gap placebo **+4.36**, break-even 93.6
  bp/side, turnover 0.15 (vs S6's 0.61); design (352 sessions) Sharpe 3.69, net@3 +3.56.

### The SEVEN kill-guards (recorded VERBATIM in each leg's `guard_mandatory.seven_kill_guards`)

Adjudicated on the FORWARD log, exactly as L12's four pre-sizing gates are recorded-not-auto-coded; the
code's standing per-leg kill switch (N_min=40, drop at one-sided upper-95% < 0) also applies underneath.

1. **60-session minimum** before any verdict on the leg.
2. **Kill if the forward gross Sharpe is < 0** over the trailing 60 sessions.
3. **Kill if net Sharpe @ 3 bp/side is < +1.0** over the trailing 60.
4. **Kill if the one-day-gap re-entry placebo Sharpe is < +2.0.**
5. **Kill if the single-names sub-book Sharpe is < +1.5.**
6. **Data-continuity VOID rule** — treat ANY feed/expiry change (OPRA vendor/feed, expiry cycle,
   strike-ladder convention, panel schema, or weeklies/0DTE entering the volume-OI proxy) as **VOIDING**
   the accrued log, not degrading it: a voided log is discarded and a NEW frozen forward test begins; a
   data discontinuity is NEVER silently absorbed as a bad forward result.
7. **Monthly coverage check** — each month verify the OPRA panel actually covered that month's monthly
   (3rd-Friday) expiries for the single-name universe (front AND next monthly); a month with missing or
   partial coverage is VOID for that month, not a zero.

### Caveats, all load-bearing, and S6's OPEN vol-exposure risk

Recorded on both legs' `guard_mandatory.open_risks`: **(a)** only 2.5y of expired-OPRA history (held-out
260 sessions); **(b)** MONTHLY-EXPIRY-ONLY — weeklies/0DTE, now the majority of single-name option
volume, are absent from the OI proxy; **(c)** VOLUME is not open interest; **(d)** the named
dealer-gamma **mechanism is mis-named** (a raw call/put volume imbalance does as well — hence L14);
**(e) OPEN vol-exposure risk** — S6 is legitimately correlated with implied/realised vol (+0.25 to
+0.29); cross-sectionally orthogonalising the *signal* on IV+RV cuts the held-out Sharpe 3.58 → 0.95,
while the spanning regression prices the vol-**book** loadings out (IV/RV loadings statistically zero
held-out, alpha +7.84 bp/day t +3.61). Both numbers are reported so a reader who ran only the first
does not reach the opposite conclusion; the forward log must watch the unhedged vol tilt.

### Accounting

Both legs are `ACTIVE_UNSIZED` at **0.0** budget, **excluded from the combined sized book** (never
added to `contributions`), and kill-switched forward. Each carries its own
`declared_trials_in_leg_family = 48` (24 formulas × 2 horizons; the null ran over all 48 cells) for its
own DSR. Because both are UNSIZED/logging-only and carry no combined-book weight,
`combined_gate.declared_trials_now` **stays 8** — exactly as L8/L10/L11/L12 did not raise it. The
`risk_budgets_active_v11` deployed dict is **UNCHANGED**: the four SIZED legs (T3, DUALCLASS, T12CEF,
ORB) still carry 1/4 each summing to 1.0, and L13/L14 join L7–L12 at ZERO. Every existing per-leg
`spec_sha256` is byte-identical to v9 (L1/L2 carry none; DUALCLASS 1e9834e3, T7 fc123807, T12CEF
c60ceb57, ORB b875c2fc, XS_GLSR_Z 0df494cf, XS_SMART 28bb4edc, CEFMUNIEQ 7af4baa2, ETFRV_Z20 b572b0a6,
DUALCLASS_EXIT10 1e0ab117, CRYPTO_LOWVOL 08f7e5a1). The per-leg kill switch, the T-bill benchmark, the
as-of/lookahead guards, the no-pre-freeze-row guard and `minimum_before_verdict` are untouched.

*Tenth freeze appended 2026-08-23. ADDITIVE, LOGGING-ONLY. Two UNSIZED options-flow challengers, the
last additions before the forward clock starts. Frozen instrument. No orders, no real money, no
purchases, no commit by the logger; free/cached data only (one added read-only local cache: the frozen
expired-OPRA options panel — no options venue, no key, no fetch). `preregistration_sha256` re-pinned to
this extended .md (v9 hash preserved as `preregistration_sha256_v9`). Every backtested number herein is
a selection-inflated upper bound; the forward log is the only evidence, and it is empty.*
