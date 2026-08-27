# STRATEGIST decision — 2026-08-25 00:00 CEST (durable tick, CHUNK A)

**Status of the direction: CONVERGED and now in its WAITING regime. No pivot. One addition (T33), two
housekeeping tasks (T34, T35). Nothing killed today except what the frozen T32 protocol already killed.**

## 1. State of play, verified on disk this tick (not from memory)

| clock | verified state | next gate |
|---|---|---|
| **T30 borrow-fee collector** | `ledger.json`: 1/1 clean (2026-08-24). Cron 16:30 fired on 08-24 and correctly skipped ("already clean"). Day-1 caveat: the 08-24 snapshot was the *manual* 03:08 CEST fetch (IBKR stamp `2026.08.23 21:04`); from 08-25 on, every row is the 16:30 CEST / 10:30 ET intraday stamp. Day 1 is therefore a pre-market file, days 2+ are mid-session files. **Recorded now, before any rate is read.** | day-30 preferred-RV read ≈ **2026-09-22** |
| **T31 Deribit wing-quote collector** | 1/1 clean (manual first run 15:07 CEST). First *cron* run is 02:15 CEST today — unverified as of this tick; the 03:00 tick must check `ledger.json` shows 2/2. | collector gate ≈ 2026-09-23; convexity pre-registration not before ≈ 2026-12-22 |
| **T32 SPX box RTH probe** | **DEAD, PERMANENTLY.** 13/13 clean RTH snapshots, market open. Primary 2027-08-20: session-median executable **2.958 %** vs DTB3 **3.71 %** = **−0.75 pp**; mid 4.32 % (+0.61 pp) is unreachable at four legs; even p90 executable (5.31 %) is context only. Same sign as T25 (−3.65 pp closed-market) and the 15:00 preflight (−0.95 pp). Third probe; the frozen protocol forbids a fourth. **The last rate-level claim in the programme is closed.** | none |
| **BASKET1 v8 forward** | Clock is **advancing by design, not stuck**: the runner logs only sessions whose settlement data has cleared Alpaca's free-tier recent-SIP embargo (~1–2 sessions). At 00:00 today it reported `no_session`, `latest_free_session 2026-08-21`, `post_freeze_unlogged_candidates []` — i.e. 08-24 (the first true post-freeze10 session) is still embargoed. Its row lands automatically 08-25/26. 2 rows on the ledger (both 08-23 proof runs), 0 settled observations. **Untouched, as the 08-24 hard rule requires.** | first per-leg kill-switch reads (N_min=40) ≈ mid-Oct; combined verdict needs 252 sessions |
| **T4 paper (SPY overlay)** | 7 log rows, last settled 2026-08-21, curves ≈ −0.16 % model vs −0.23 % benchmark. Owner-gated; not touched. | — |
| **Window-2 (memecoin deadness-screen OOS)** | **NOT running.** `supervisor_state.json`: `quarantine = Q07_stage_failed` at stage `transaction_bodies`, last heartbeat **2026-08-16 19:56 CEST**, last poll 08-13, supervisor pid 2160263 dead, lock files stale. Stderr: `ConnectionResetError` from the Chainstack RPC. FINDINGS §10 has said "running" for nine days — corrected this tick. | T34 (below) |

Nothing on this table is a number I was not allowed to read: no pair-level borrow rate, no Deribit
wing, no basket leg P&L.

## 2. Decision — where to focus, and why

**Focus: the forward-data spine, extended into the goal universe. The programme is waiting on
calendar time; the only free lever left is to make that waiting time collect MORE decisive data,
not to sweep burned data.**

The 08-24 decision stands and is now mechanically complete (T30 live, T31 live, T32 dead). The
question for this tick is what ticks should *do* for the ~29 days until the first gate. Three honest
options were weighed:

1. **Do nothing but verify ledgers.** Cheapest and disciplined — but the programme's stated goal is a
   *US-equities/ETF* bot, and the only convexity panel we are collecting (T31) is BTC/ETH. If bought
   convexity survives on Deribit in December, it still would not be in the goal universe.
2. **Run a pre-registered single design on the free expired-OPRA daily-bar panel (2024-02→).** Rejected:
   those are trade-price bars with no bid/ask; a bought-wing strategy's cost *is* the bid/ask, so the
   panel cannot price the claim honestly — this is exactly the "free data prices a statistic, never a
   claim" wall again, and 2.5 years of a skewed payoff has no power at the honest bar anyway.
3. **Stand up the same forward collector T31 is, but on Alpaca's free US options snapshot endpoint** —
   which T32 just proved (13/13 clean pulls, ~5.6k strike pairs per expiry per snapshot, full chains
   with bid/ask under the paper keys). **Chosen.** It is a collector, not a sweep; the build pattern
   is proven twice (T30, T31); the cron slot is a one-liner; and it is the only way the convexity
   question can ever be answered *in the universe the goal names*, with real quotes, for zero dollars.

**T33 — daily Alpaca US-options wing-quote forward collector** (queued `pending`, priority 1, assigned
to the 03:00 CHUNK B tick today):
- Underlyings: SPY, QQQ, IWM, TLT, HYG, GLD, XLE, XLF + NVDA, TSLA, AAPL, AMZN, MSFT, AMD (14; the
  builder may trim to fit the rate limit, but must record the final list before the first snapshot).
- One snapshot per trading day at **15:45 ET (21:45 CEST)** — inside RTH so quotes are live, before the
  closing crush. All expiries ≤ 45 DTE plus the next two monthlies; full chain (bid/ask/size/last, IV and
  greeks as served). `/v1beta1/options/snapshots/{underlying}`, `limit=1000` + `page_token`, 429 backoff —
  the T32 fetch, unchanged.
- Manifested (sha256 per day), completeness ledger, non-t4 cron line `45 21 * * 1-5`.
- **Kill-condition, frozen now:** ≥ 95 % clean days over the first 30 trading days or fix/kill the
  collector. **No strategy number is read before +120 calendar days (≈ 2026-12-23).** The convexity
  design (trigger, bar, multiple-testing cost, kill) is pre-registered *before* the panel is opened, and
  is the same document as T31's so the two universes share one bar.
- **Honest expectation, written before a single quote is stored:** T21 §4b established the variance
  premium is real and powered (+4σ); *buying* convexity therefore has negative expected carry by
  default, and a bought-wing design survives only if a conditional trigger beats that carry after its
  multiple-testing cost. The collector makes the claim *testable*; it does not make it likely.

**T34 — window-2 collection is quarantined, decide and resume or archive** (`pending`, priority 2).
Facts above. The supervisor has a documented `clear_quarantine` resume path but its own design says a
stage interrupted mid-flight (Q07) must not be resumed from a partial artifact; the right move is a
stage restart of `transaction_bodies` from its checkpoint, launched **detached**, never inside a tick.
This is the OOS test of the programme's only surviving positive (the B20B deadness screen); leaving it
silently dead for nine days was a discipline failure and is now on the record.

**T35 — hash-pin the evaluators before the panels mature** (`pending`, priority 2). Write and sha256-pin
(a) the T30 day-30 evaluator script that implements `T30_BORROW_FORWARD.md` §evaluation mechanically,
run only as a format check on day-1 data; (b) the joint T31/T33 convexity pre-registration document
(design, bar, multiple-testing cost, kill-condition) — written now, opened in December. Zero numbers
read. This is the freeze-then-test discipline applied to our own future selves.

## 3. What would prove this direction dead (unchanged, now with dates)

- **T30 (≈ 2026-09-22):** fewer than ~10 of the 113 preferred-RV pairs with both legs borrowable below
  the pair's measured gross edge → preferred-series RV is permanently dead.
- **T31 / T33 collector gates (≈ 2026-09-23 / ≈ 2026-10-07):** < 95 % clean days → fix or kill.
- **Convexity pre-registrations (≈ 2026-12-22):** the frozen designs die at the honest bar in *both*
  universes → bought convexity is dead on free forward data.
- **BASKET1:** per-leg kill-switches fire as they reach N_min = 40 (first reads ≈ mid-October).
- **The direction as a whole:** T30 kills preferred-RV **and** both convexity designs die → the free-data
  programme is **EXHAUSTED**, and the fork — pay for data (DATA_PURCHASE_SCOPE: Ortex Advanced ~$99/mo is
  the only defensible line item; historical options quotes are the other) or stop — goes to the owner
  as one decision. Not before.

## 4. Standing directive for the waiting regime (all ticks)

- **CHUNK A** ticks: verify the four ledgers (T30 `days_clean`, T31 `days_clean`, BASKET1 row count and
  `no_session` reason, T33 once live), record any collector fault, and stop. Short by design.
- **CHUNK B** ticks: T33 build (today 03:00) → T34 → T35, in that order. **No new free daily/intraday
  cross-section sweeps** — the category stays closed (three consecutive honest zeros; pooled bar predicts
  zero survivors ex ante).
- **Never:** add a basket leg, re-pin the basket freeze, read a gated number early, touch t4.
