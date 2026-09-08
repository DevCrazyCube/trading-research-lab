# STRATEGIST decision — 2026-08-28 00:00 CEST (durable tick, CHUNK A)

**Direction: unchanged and CONVERGED — the forward-data spine (T30 borrow, T31 Deribit, T33 US
options) plus the untouched live clocks (BASKET1 v8, T4, window-2), in its WAITING regime. No
pivot, nothing killed, no gated number read in the goal universe, no new sweep, no task promoted.
Every clock moved as scheduled. Two process items are ledgered (§4): a silent 15:00 tick and an
unledgered window-2 watchdog. One read-slip is confessed (§4c). Nothing goes to the owner beyond
the standing recommendations.**

## 1. Ledgers verified on disk this tick (00:00–00:20 CEST) — read-only, counts only

| clock | state | fault? | next gate |
|---|---|---|---|
| T30 borrow | **4/4 clean** (08-24…27; 08-27: 19,720 rows, 379 pref, 596/602 universe). Day 5 captures 16:30 today. Pin set (doc, collector, universe, evaluator, B01 pair record) `sha256sum -c` **all OK**. | none | day-30 ≈ 09-22/23 |
| T31 Deribit | **4/4 clean** (08-27 02:16: 1,774 rows, BTC 350/350, ETH 326/326, delivery +2). Day 5 captures 02:15 today (after this tick). Pin OK. | none | ≈ 09-23; design read 12-23 |
| T33 US options | **2/3** (08-25 failed pre-v2, **08-26 + 08-27 clean**; 08-27: 38,285 rows / 14 underlyings / 73.9 s). Pins doc+script **OK**. **HYG fresh 0.626→0.631→0.637 and XLE 0.700→0.680→0.689: both `fresh_ok` on 0/2 clean days.** The frozen §2 eligibility rule (≥ 95 % of clean days, evaluated ≈ 10-07 before any design number) already puts both on course for exclusion — and the pre-registration *stated this expectation ex ante* ("HYG excluded; XLE/XLF at risk"). No amendment, no threshold move; the December design runs on whatever set the rule yields (expected 12 names). | none | day-30 ≈ 10-07 |
| BASKET1 v8 | log **5 rows** (last session 08-26, logged 08-27 09:00); frozen `d53b4fe4…` mtime 08-23 — **untouched**. The 00:00 `basket_forward session` ran OK; session 08-27 is expected at the 09:00 run (free-tier SIP embargo). Curve values not read. | none | per-leg N_min 40 ≈ mid-Oct |
| T4 paper | **10 rows** (+1, 08-27 21:50); not touched, not read | — | — |
| Window-2 (T34) | `raw_transaction` **337,125** at 00:02 vs 266,257 at 08-27 12:00 → **+70,868 in 12 h ≈ 142k/day** (≥ 100k/day rule: PASS). Failed exits **08-27 final: 8/20** (was 1 at 12:00; 08-26 final was 12) vs the 20/day BLOCKED rule: PASS. 24 rc=1 exits since 08-24. Loop alive (bash 5683 → python 187729, attempt 7 since 21:20Z). Remaining 5,484,133 − 337,125 = 5,147,008 ≈ 36 days → raw phase ≈ **2026-10-03** (was 09-30/10-01; hard min unchanged 09-11). See §4b for the watchdog. | none | pre-registered OOS read after decode gates |
| CONVEXITY prereg | doc + `convexity_design_costing.py` + costing JSON + `convexity_evaluate.py` `sha256sum -c` **all OK** | none | first reading 2026-12-23 |
| NEWSDESK1 | ledger 11 rows (2 setups, 9 abstentions); 2/30 resolved, 0 open; kill ALIVE. 18:00 tick found the ranked stream ~16.5 h stale — no slot pairs a fresh catalyst with a fresh price (recommendation stands, §5). | process, not evidence | needs 30 resolved |
| PREDMARKET1 | ledger 64 rows (47 estimates, 17 abstentions); 21:00 tick froze 12 more; **0/50 resolved, 47 open**; kill ALIVE. Scorer must dedupe by `market_id` keep-first. | none | 09-06 / 09-13 / 09-20 / 10-09 |

Owner channels **moved** (`DECISIONS.md` +62 lines 23:01, `agent_discussion.md` +212 lines 23:47, both
08-27) — but the content is the memecoin side's Claude↔Codex chain (AFTERSHOCK execution-realism
engine, handoffs 422→424; Codex's second adversarial audit is a **NO-GO**, handoff 424 queued for the
interactive Claude session; Sniper V3 retired, MEMEBOT halted-decider = entry gate, EVO V2 at gen 0).
**No owner decision on the equities direction is in either file.** Handoff 424 is an interactive-session
build, out of scope for a bounded durable tick and not claimed here.

## 2. Where to focus, and what proves it dead (unchanged — restated, not re-derived)

There is still no live directional candidate in the goal universe, and the free-data sweep
category stays CLOSED (four consecutive honest zeros through INVENT_2026-08-27). The programme's
next genuine *decision* remains the **T30 day-30 read ≈ 09-22** on same-issuer preferred-series RV
— the only object with an already-replicated gross edge (t 7.49, OOS gradient, held-out net +0.93)
waiting on exactly one measurable input (borrowability of both legs). **Dead if**
`t30_borrow_evaluate.py --evaluate` finds < 10 of 113 pairs with both legs borrowable at a fee
below that pair's measured gross edge. Second: bought convexity D1/D2/D3 on 12-23 (prior: all
dead; T33 set expected to be 12 names). Third, outside the goal universe: window-2 B20B OOS after
the decode gates (raw phase ≈ 10-03). If T30 **and** both convexity designs die, ONE pay-or-stop
fork goes to the owner with the frozen three-item paid-data menu (borrow-availability feed,
bond/credit-ETF NAV, non-US trust NAV) — not before 12-23, and the menu does not grow.

Convergence check, stated plainly: the honest move this tick is to **hold**. Every candidate
direction that could be opened now on free data has a pooled bar that predicts zero survivors ex
ante; opening one would be padding, not progress. The clocks are the work.

## 3. Process moves this tick

- **No task promoted, killed or re-ordered.** T34 stays `running` (142k/day, 8/20). T30/T31/T33
  stay `done` (clocks run themselves). Nothing is due before 09-06 (first PREDMARKET resolution) /
  09-22 (T30 read).
- **Agenda note appended** with this tick's counts and §4.
- Memory (`aftershock-v2-payable-absorption`) gets a one-line 08-27 state update so the next
  interactive session does not re-derive the Codex NO-GO.

## 4. Process items ledgered

**(a) Silent 15:00 tick.** `cron.log` shows the 08-27 15:00 durable tick started its headless Claude at
15:00:24 → `claude_20260827_h15.log` is **0 bytes**, and no 15:00 CHUNK B entry exists in FINDINGS or
the agenda note. The 18:00 tick ran normally. Consequence: one INVENTION slot produced nothing —
which, given the standing abstention rule, is the *same outcome* as a compliant tick, so no evidence
was lost. Recommendation (process file, owner/interactive call, not actioned): `durable_tick.sh`
should append an explicit `NO OUTPUT` marker to FINDINGS when the Claude log is empty, so a silent
tick is visible on the ledger instead of only in cron.log.

**(b) Window-2 watchdog, unledgered until now.** `research/b11m_window2/free_decode_watchdog.sh`
(mtime 08-27 15:40, crontab `*/2`) relaunches `run_free_decode.sh` verbatim (same endpoint/args, T34
§5.3) only if the loop is down and the `COLLECTION COMPLETE (rc=0)` marker is absent. It was
created during/after the silent 15:00 slot and has no FINDINGS entry; this note is its first. It
did relaunch the loop (attempt numbering reset to 1 on the 08-27 afternoon; attempt 7 running).
Verified benign: read-only public RPC, no metadata drift, idempotent resume.

**(c) Read-slip, confessed.** While counting the AFTERSHOCK resolution ledger I printed pooled
`realized_r` sums across all 24,089 rows (23,368 control / 721 treat). Per `DECISIONS.md` 08-27 the
post-reset V1–V5 books are **BURNED / plumbing-only**, so the numbers are not evidence of anything;
they were not used for any decision and are not reproduced here. Rule restated: in a waiting-regime
tick, count rows, do not aggregate returns — even on a side ledger.

## 5. Standing recommendations to the owner (unchanged, not actioned)

1. NEWSDESK slot: 06:00 has the catalyst but a stale reference; 18:00 has the price but a ~16 h
   stale ranked stream. Move NEWSDESK to ~13:30–14:30 UTC or add a recency weight as a NEW frozen
   instrument; swap 06:00 → PREDMARKET.
2. Commit the disclosed uncommitted diffs (`b9d_transaction_bodies.py` OSError-retry; the
   08-27 honest-measurement overhaul) — ticks never commit.
3. PREDMARKET scorer: dedupe by `market_id` keep-first before the 09-06 first resolution.

## 6. Next ticks

- 03:00 CHUNK B: abstain unless a published-synchronous-tether or forward-panel family outside the
  dead ledger exists (one paragraph). T31 day 5 lands 02:15 — verify.
- 12:00 STRATEGIST: verify T30 day 5, T33 day 3 (HYG/XLE 0/3 expected), BASKET1 session 08-27 at
  09:00, window-2 08-28 failure count and rate.
