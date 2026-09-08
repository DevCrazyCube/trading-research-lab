# PRE-REGISTRATION — PREFRV forward paper design for the T30 ALIVE branch (task T39)

**Written and sha256-pinned 2026-08-30 15:00 CEST (durable supervisor, CHUNK B), on clean day 7 of the
T30 borrow collector, BEFORE the day-30 verdict exists and BEFORE anyone has read a pair-level FEERATE,
AVAILABLE, or any price after the 2026-08-14 design-cache end.** Research / paper only. No orders, no
money, no broker authentication. Standalone ledger `PREFRV_FORWARD_*` — **NOT a BASKET1 leg**
(`BASKET_FORWARD_FROZEN.json` untouched, hard rule 2026-08-24).

Inputs read to write this: `research/trading_bot/T30_B01_PAIR_EDGES.json` (aggregate counts only),
`scripts/trading_bot/t30_borrow_evaluate.py` (as code: the alive rule), `T30_BORROW_FORWARD.md`,
`BORROW_FEED_SCOPE.md` §4, `INVENT_0822_MASTER.md` §3.1, `invent0822_preftether.py` (as code: the
state machine and cost model), `INVENT_0822_pairtether_B.json` (aggregate). **Not read, by rule:**
any `research/data/borrow_forward/extract/*.json`, any pair-level fee or availability figure, any bar
after 2026-08-14. `research/data/borrow_forward/ledger.json` was read for its `summary` counts only
(6 attempted / 6 clean at 2026-08-29 16:30).

---

## 0. TL;DR

- **Object.** Same-issuer preferred-series relative value (INVENT_0822 B01): the programme's only
  tether-confirmed object (design gross t 7.49 vs pooled bar 3.33; monotone tether gradient
  3.41/1.02/0.55 replicated OOS 3.08/0.95/0.14; ρ1(Δs) −0.245 PASS), unpromotable on borrow (0/113 pairs
  both-shortable at Alpaca) and on net significance (held-out net +9.6 bp/wk, **t 1.48**, dies at 2×
  spread). T30 measures the borrow wall with IBKR's loan-desk file; the pinned evaluator returns
  `BORROW_WALL_PASSED` iff ≥ 10 of 113 pairs are both-borrowable at fee < gross edge on clean day 30.
- **What this document does.** Freezes, *before* that verdict, exactly what forward paper test runs if
  the wall is passed: the alive set (= the evaluator's list, verbatim), the design-identical state
  machine, the cost model (frozen half-spreads + SEC §31 + **realised** T30 borrow fee charged
  forward-only), sizing, per-pair and pooled kill-switches, the verdict rules, N_min / N_max, the
  multiple-testing charge, and the ledger names.
- **The honest power statement (§8).** From frozen aggregates alone, a forward book on the ≥ 10-pair
  alive floor needs ≈ **4,400 book-weeks** to detect the design-window net at 80 % power; the full
  113-pair book needs ≈ 390 (7.5 years). The forward test therefore **cannot confirm the design net on
  any human calendar**. What it *can* do: (a) **kill** a net that is genuinely negative (N_min = 40
  book-weeks), (b) **replicate or refute the gross tether** (36–134 weeks depending on alive count), and
  (c) return ALIVE only if the realised net is a **multiple** of the design net (≈ 2–7× at 52 weeks).
  Stated expectation: **UNDECIDED → RETIRED "unproven"** (or DEAD). This is written so that a survivor
  would be an unmistakable surprise, not a tuned confirmation.
- **Kill for T39 itself:** T30 verdict `PERMANENTLY_DEAD` → this design is closed unused ("branch not
  taken"), $0. Once live: the pinned rules in §6–§7; no re-freeze, no retune, ever.

---

## 1. Preconditions to START (mechanical; the runner refuses otherwise)

1. `research/trading_bot/T30_BORROW_VERDICT.json` exists, written by the T35-pinned
   `t30_borrow_evaluate.py --evaluate` (pin set `T30_BORROW_FORWARD.sha256` verified at run time), with
   `verdict == "BORROW_WALL_PASSED"` and `clean_days >= 30`.
2. The pins in `PREFRV_FORWARD_PREREGISTRATION.sha256` (this doc, `prefrv_forward_power.py`,
   `PREFRV_FORWARD_POWER.json`, the three frozen INVENT_0822 cache files, and — after amendment A1 — the
   runner `scripts/trading_bot/prefrv_forward.py`) verify.
3. `PREFRV_FORWARD_STATE.json` does not already exist (a forward book is started **once**).
4. Owner has not vetoed T39 in `DECISIONS.md` (a veto = "design in an attended session before the alive
   list is seen"; the runner checks for the literal string `T39_VETO`).

## 2. Universe — the alive set, verbatim

- **Alive set = exactly the pairs with `alive == true` in `T30_BORROW_VERDICT.json.pairs`**, in file
  order. No re-ranking, no hand selection, no liquidity/half-spread/OU sub-screen, no cap on count.
  (The 08-22 trap: the six OU-gated "best" pairs B04/B16 died to a matched-size null; picking is
  forbidden.)
- Each pair keeps its design identity: legs `a`,`b` (Alpaca `X.PRy`), IBKR legs via
  `alpaca_sym.replace(".PR", " PR")`, `root`.
- A pair leaves the alive set only by the retirement rules in §4.5 / §6. Nothing enters after start.

## 3. Signal and state machine — identical to the 08-22 design (`invent0822_preftether.py` B01)

- **Grid.** Weekly grid = every 5th NYSE session. The design grid is `days[::5]` of the frozen cache,
  last grid session **2026-08-14**. The forward grid continues it: forward grid session *g* is the
  *5g*-th NYSE trading session strictly after 2026-08-14 (g = 1 → 2026-08-21, g = 2 → 2026-08-28, …;
  holidays are simply not sessions). **Start session** = first forward grid session strictly after the
  date in `T30_BORROW_VERDICT.json.evaluated_at`. Book is flat at start.
- **Spread.** `s_t = ln(RAW_a,t) − ln(RAW_b,t)` from **raw** (unadjusted) official closes on grid sessions.
  **z.** trailing `Z_L = 52` grid sessions, excluding *t*: `z_t = (s_t − mean)/sd(ddof=1)`, valid only if
  ≥ 26 finite points and sd > 0. The trailing window may reach back before the start session (price
  history is signal input, not evidence; it is fetched at run time, never read for this document).
- **Returns.** `r_t` = grid-to-grid simple return from dividend-**adjusted** closes (`adjustment=all`),
  per leg; pair P&L per book-week `= w · (r_a − r_b)`. Levels from raw, returns from adjusted, exactly
  as the design (adjusted levels inject a coupon-difference drift into the ratio).
- **Rule (frozen constants `Z_L=52, Z_K=2.0, Z_X=0.5, MAXHOLD=26`).** At grid session *t*, in this order:
  (1) exit an open position if `|z_t| ≤ 0.5`; (2) exit if `age ≥ 26` grid sessions; (3) exit if either
  leg's return to *t+1* is not finite (missing print) — see §4.5; (4) if flat and `|z_t| ≥ 2.0`, enter
  `w = −sign(z_t)` (`w=+1`: long a / short b; `w=−1`: short a / long b) **subject to the borrow gate in
  §4.3**. Position weights are ±1 per pair, dollar-neutral. Same-session exit-and-re-enter is impossible
  by construction (|z| ≤ 0.5 and ≥ 2.0 are disjoint).
- **Fill.** Primary series **P**: fills at the grid session's official close — the design's own
  convention (the ρ1 bounce gate passed at −0.245 in both windows, which is why the design was allowed
  to use its own print). Diagnostic series **D1** (recorded every week, never promoted, but a *required
  sign witness* for ALIVE, §7): identical signals, fills at the close of the **session after** each grid
  session (the "instant, not interval" rule earned 2026-08-22).

## 4. Execution and cost model

### 4.1 Half-spread (frozen, both legs, per unit turnover)
`hs_pair = max(median_half_bp[a], median_half_bp[b])` from the frozen point-in-time NBBO snapshot
`research/data/inv0822_tether/pref_halfspread.json.gz` (sha pinned in the `.sha256`; design measured
median 17.5 bp). Charged as in the design: `cost_spread = |Δw| · (2 · hs_pair + SEC31)` per pair-week,
with `SEC31 = 0.278 bp`; i.e. both legs pay the *worse* leg's half-spread on entry and on exit.
The runner also snapshots `/v2/stocks/quotes/latest` for the alive legs at fetch time each week
(realised half-spread, **reported**, used only in the §7 promotion guard, never in P&L).

### 4.2 Borrow fee — realised, forward-only, never back-filled
For each pair-week held (grid *t* → *t+1*), the short leg's fee accrues per calendar day *d* in
`(date_t, date_{t+1}]`: `fee_d = FEERATE_short,d / 100 / 365` on 1.0 notional, where `FEERATE_short,d`
is the short leg's `FEERATE` in that day's **clean** T30 extract (`research/data/borrow_forward/
extract/extract_d.json`); on a day without a clean extract, the last clean value carries forward
(weekend staleness is expected, `T30_BORROW_FORWARD.md` ops note). Fees are read only for days
≥ the start session and only for the actual short leg; the design's flat 200 bp/yr is **not** used.
Missing fee for a held short leg on ≥ 5 consecutive calendar days → treat as a recall (§4.4).

### 4.3 Borrow gate on entry
Entry at grid session *t* requires the intended short leg to show `AVAILABLE > 0` in the clean extract
of date *t* (or the last clean extract before *t*, if *t* has none). Otherwise **no entry**; the week is
logged as `skip_no_borrow` for that pair (a count that is itself a finding about executability).

### 4.4 Recall while holding
If the short leg shows `AVAILABLE == 0` on **two consecutive clean extracts** while a position is open,
the position is closed at the close of the **next grid session** with the normal exit cost **plus one
extra `hs_pair`** (recall-slippage proxy, declared now). Logged `exit_recall`.

### 4.5 Redemption / delisting / missing prints
A preferred series that is called, redeemed, or stops printing: if a leg has no official close for
5 consecutive sessions, the pair is closed at the last available close of both legs (normal exit cost)
and **retired permanently** from the alive set (`retire_no_print`). A called series redeemed at par
before the next grid session: the adjusted-return series carries the redemption cash; the pair is
closed at that return and retired (`retire_called`). Retirements are not kills and are not replaced.

### 4.6 Sizing
Unit book: $1 long / $1 short per active pair (dollar-neutral within the pair), **equal-weight across
active pairs**; the book-week return is the plain mean over active pairs of `(w·(r_a − r_b) −
cost_spread − fee)` in bp, exactly the design's `book()` aggregation. A week with zero active pairs is
**not an observation** (the design skips it; a zero would dilute the mean). Paper only; dollars are
irrelevant, the ledger tracks bp on a unit book. The short leg's `AVAILABLE × price` is recorded weekly
as a capacity note, with no verdict role.

## 5. Ledger and artifacts (names frozen)
- `research/data/prefrv_forward/` — weekly Alpaca daily bars (feed `sip`, `adjustment=all` and `raw`,
  the two files the design cache was built from) for the alive legs, append-only per week with a
  `manifest.json` of sha256 + row counts; quote snapshots; nothing rewritten.
- `research/trading_bot/PREFRV_FORWARD_LOG.jsonl` — one row per pair-week (pair, w, z, r_a, r_b, gross,
  cost_spread, fee, net, flags) and one `book` row per grid week (P and D1 means, n_active).
- `research/trading_bot/PREFRV_FORWARD_STATE.json` — open positions, ages, N book-weeks, retirements.
- `research/trading_bot/PREFRV_FORWARD_VERDICT.json` — written by the runner's `--verdict`, applying §6–§7
  verbatim; once it says DEAD / ALIVE / RETIRED it is never overwritten.
- `PREFRV_FORWARD_POWER.json` — the §8 arithmetic (pinned).

## 6. Kill-switches (mechanical; the runner applies them every grid week)
- **Per-pair drop.** After `n_p ≥ 26` active pair-weeks, if the one-sided upper 95 % bound of that
  pair's mean net (`mean + 1.645·sd/√n_p`) is `< 0`, the pair is **dropped permanently** (`drop_neg`).
  Its slot is not reallocated; it keeps counting in every pooled statistic through its drop date.
- **Pooled DEAD (net).** After `N ≥ N_min = 40` book-weeks (series P), if the one-sided upper 95 % bound
  of the mean net book-week return is `< 0` → **DEAD**. (Same rule as BASKET1's leg kill.)
- **Pooled DEAD (tether).** After `N ≥ 40` book-weeks, if the mean **gross** book-week return `≤ 0` →
  **DEAD, "tether failed forward"** (the gross replicated 3.41 → 3.08 in the two historical windows; a
  gross that cannot beat zero forward means the object itself is gone, not just its cost).
- **Executability DEAD.** If, by `N = 40`, fewer than 3 distinct issuers ever held a position (borrow
  gate + retirements), the alive set is not a book → **DEAD, "not executable"**.
- A DEAD verdict is permanent. No re-freeze, no threshold change, no second design on this object.

## 7. Verdict rules (checked weekly; ALIVE first eligible at N = 52)
Let `N` = book-weeks in series P, `m`, `t` = mean and t-stat of net book-week returns (plain, iid weeks;
also report Newey-West lag-4).
- **ALIVE** requires ALL of: `N ≥ 52`; `t ≥ 2.0` (one-sided replication bar); `m ≥ 9.6 bp/wk` (the
  design's own held-out net — a forward "survivor" must at least reproduce the magnitude it was frozen
  on; distance from zero, not just significance); gross `t ≥ 2.0`; **D1** mean net `> 0` (sign witness:
  the edge must survive a one-session fill delay); no single pair contributes `> 40 %` of cumulative
  net gains; ≥ 3 distinct issuers with positive cumulative net.
- **PROMOTABLE** (= ALIVE **and** the INVENT_0822 §3.1 guard, verbatim): alive set at verdict ≥ 30
  pairs **and** realised median half-spread of the traded legs (weekly quote snapshots) ≤ 9 bp. A
  PROMOTABLE verdict is a research finding that opens an **execution conversation with the owner**;
  it is not a licence and not a basket leg.
- **UNDECIDED** otherwise, continuing to `N_max = 156` book-weeks (3 years, ≈ 2029-09), then
  **RETIRED "unproven"** permanently. No extension.
- Nothing below is ever re-read after a terminal verdict; the runner refuses to run on an existing
  terminal verdict (T36 precedent).

## 8. Power — computed from frozen aggregates only (`prefrv_forward_power.py` → `PREFRV_FORWARD_POWER.json`)
Held-out net +9.6 bp/wk at t 1.48 over 132 book-weeks ⇒ sd ≈ **74.5 bp/book-week** with ≈ 23.6 active
pairs/week (weekly SR 0.129, annual 0.93 ✓). Each pair is active ≈ 19.8 % of weeks (median 86/434), so
an alive set of *n* pairs averages ≈ 0.198·n active pairs; under independence sd scales as √(23.6/k)
(same-issuer correlation makes it worse, so these are **upper bounds on power**). One-sided α 5 %,
power 80 %:

| alive pairs | active/wk | sd (bp) | weeks to detect design **net** | weeks to detect design **gross** | detectable net @52 w | expected t @52 w if design net true | × design net needed for ALIVE @52 w |
|---|---|---|---|---|---|---|---|
| 10 | 2.0 | 257 | **4,430** | 403 | 89 bp | 0.27 | 7.4 |
| 20 | 4.0 | 182 | 2,215 | 201 | 63 bp | 0.38 | 5.2 |
| 30 | 5.9 | 148 | 1,477 | 134 | 51 bp | 0.47 | 4.3 |
| 60 | 11.9 | 105 | 738 | 67 | 36 bp | 0.66 | 3.0 |
| 113 | 22.4 | 76 | 392 | 36 | 26 bp | 0.91 | 2.2 |

Reading: **N_min = 40 is a kill-power choice, not a confirm-power choice** — at N = 40 the upper-95 %
rule kills a book whose true net is ≲ −1.6·sd/√40 (≈ −65 bp/wk at 10 pairs, −19 bp/wk at 113); it will
not kill a true small positive. `N_max = 156` is where even the full book would only reach expected
t ≈ 1.6 at the design net, i.e. where continuing cannot change the answer. An ALIVE verdict at N = 52
needs the realised net to be **2–7× the design net**. That is the bar, stated now, on purpose.

## 9. Multiple-testing charge
This is **trial 1 of the PREFRV forward family** (declared_trials = 1; the design-window gross was
never charged as a forward claim). Upstream selection is disclosed, not hidden: B01 was 1 of 21 scored
cells in the 08-22 preferred theme (theme noise bar t 2.73, cleared at 7.49 and replicated OOS). The
programme MT ledger is charged **+1** when the book starts. There is no second trial: a DEAD or RETIRED
verdict closes preferred-series RV on free data for good.

## 10. Stated prior (honest, before the data)
`BORROW_FEED_SCOPE.md` §4 already said it: resolving borrow does not promote B01, because the net is
insignificant at 1× spread and negative at 2×. The alive set will be a *subset* of the 113 pairs
(likely the mega-bank names IBKR lends freely), which lowers power further (§8). Expected forward
outcome, in order of probability: UNDECIDED → RETIRED "unproven"; DEAD on net at N ≈ 40–80; gross
replicates (t ≥ 2) while net stays sub-bar — the cleanest possible statement that *the tether is real
and the spread eats it*. ALIVE would mean the design understated the edge by several times; PROMOTABLE
would additionally need ≥ 30 borrowable pairs at ≤ 9 bp realised half-spread, which the design's
17.5 bp median makes unlikely.

## 11. Immutable / permitted
- **Immutable after this pin:** alive-set rule, grid, constants, fill conventions, cost model, borrow
  rules, sizing, kill-switches, verdict thresholds, N_min/N_max, ledger names, the MT charge.
- **Permitted, as dated amendments with the prior hash kept as audit trail:** A1 = pinning the runner
  `scripts/trading_bot/prefrv_forward.py` (deadline 2026-09-15, task T40) with its self-test on
  synthetic panels; mechanical resolutions of data faults (a vendor-revised bar, a symbology miss) that
  change no rule; adding a read-only reported metric.
- **Forbidden:** any change to a threshold or constant, any pair added, any re-freeze, any second
  design on this object, adding this book to BASKET1, reading pair-level T30 numbers before the
  evaluator's verdict, back-filling fees, running before §1 holds.

## 12. Kill-condition for this pre-registration itself
- T30 verdict `PERMANENTLY_DEAD` → T39 closed `killed` ("branch not taken"), the runner never starts,
  cost one tick, $0. The document stays as the record that the survivor branch was designed blind.
- Owner veto (`T39_VETO` in `DECISIONS.md`) → same closure, provided the owner's attended design is then
  pinned before the alive list is seen.

## 13. Untouched
`BASKET_FORWARD_FROZEN.json`, the t4 path, window-2, T30/T31/T33 collectors and their pins, the
convexity pins: not touched. No commit, no orders, no spend.
