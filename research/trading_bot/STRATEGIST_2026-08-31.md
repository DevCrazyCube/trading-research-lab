# STRATEGIST decision note — 2026-08-31 00:00 CEST (durable supervisor, CHUNK A)

## Checks performed this tick (all read-only unless stated)

1. **U4 / T38:** U4 is STILL ABSENT. `DECISIONS.md` contains no U4 entry (only the standing
   definition: "U4 and U5 remain a later explicit decision after collection").
   `research/b11m_window2/supervisor_state.json`: `state=all_stages_complete`,
   `results_unlocked=false`, `quarantine=null` — the earlier Q07 quarantine at
   `decode_and_reserves` has cleared and collection is complete, so the window now waits
   ONLY on an attended U4 entry. T38 stays `blocked`. Ticks never unlock; this is the
   owner's one-shot attended read (hours, $0).
2. **T30 borrow-forward feed:** `research/data/borrow_forward/ledger.json` shows
   **7/7 clean days** (2026-08-24 → 2026-08-30, 0 failed), summary updated 08-30 16:30 CEST.
   The day-7 verify the 18:00 tick skipped (it auto-stamped after doing only NEWSDESK) is
   hereby done. Day-30 read ≈ **2026-09-22**, which is also the owner's pay-or-stop fork
   date if T30 dies (08-30 00:00 re-dating stands; no owner veto in DECISIONS.md).
3. **T39 pin:** `sha256sum -c research/trading_bot/PREFRV_FORWARD_PREREGISTRATION.sha256`
   → **6/6 OK** (prereg doc, power script, power JSON, three frozen INVENT_0822 caches).
   The T30 survivor branch is pre-registered blind, as planned.
4. **T40:** `pending`, prio 2, deadline **2026-09-15** — the next CHUNK B builds the
   runner (synthetic-panel self-test only, refuses to start unless the T30 verdict is
   `BORROW_WALL_PASSED`).

## Decision: agenda hygiene — 7 stale `approved` statuses reconciled to `done`

The agenda's declared lifecycle is `pending -> running -> done|blocked|verified|killed`;
`approved` is not in it. Seven tasks sat in `approved` while each already carried an
embedded `result` with `status: done` and a recorded verdict:

| task | recorded verdict (already in the ledger) |
|---|---|
| T5_cost_realism | done — B22B slippage measured 30/30 days; p90/p95 slippage exceeds the paper edge; 36/100 ORB names unborrowable |
| T13_risk_sizing_pivot | DEAD — crash filter loses to de-risked buy&hold; vol-target edge uncertifiable (p=0.233) |
| T15_validate_pead | DEAD by insufficient power (MDE 4.44% vs 0.90% gate, 4.93×) |
| T20_fix_paper_fill | done — t4 paper fill mechanism fixed 2026-08-18 (owner-side path; agenda metadata only, path untouched) |
| T21_nondirectional_income_survey | done — 14 mechanisms ranked; funding carry #1; equity VRP DEAD on vol-matched null |
| T22_leveraged_funding_carry | DEAD at every useful leverage (borrow ≥ funding 942 straight days, t=−4.15) |
| T24_cme_basis_probe | DEAD — CME basis +2.08pp vs MDE 4.45pp, t=1.31; worse than perp funding carry |

**Why this matters:** the stale statuses made the agenda's open surface unreadable — a
future tick (or the owner) scanning for actionable work saw 7 apparently-live prio-1/2
tasks whose premises died weeks ago (carry is dead 4 ways; risk-shaping dead; PEAD dead).
After reconciliation the open surface is honest and minimal: **T38 (blocked on U4) and
T40 (pending, 09-15)**. Nothing else is live.

**Rule attached to the reconciliation:** any live follow-up from these seven must be
filed as a NEW task with its own guardrails — never by resurrecting the old status.
**Kill-condition for this decision:** an owner DECISIONS.md entry stating `approved` was
an intentional owner-gate distinct from `done` → revert the seven statuses verbatim and
re-note here.

## Direction (unchanged, converged)

Nearest read **T38** (attended, hours, $0) → **T30 day-30 ≈ 09-22** (fork date if dead;
T39's PREFRV forward design goes live if alive, runner = T40) → convexity reads 09-22 /
10-07 / 12-23 in the $0 background. Free-data sweep category stays CLOSED. What would
prove the current direction dead: T30 dead at 09-22 (→ owner pay-or-stop fork) AND the
convexity panels dead through 12-23 — then the free-data programme has no remaining
forward spine and the paid menu is the only path.

Basket frozen untouched; t4 path untouched; no commit, no orders, no spend.
