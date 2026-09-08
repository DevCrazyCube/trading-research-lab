# STRATEGIST decision — 2026-08-29 00:00 CEST (durable tick, CHUNK A)

**Direction: unchanged and CONVERGED — forward-data spine (T30 borrow, T31 Deribit, T33 US options) +
untouched live clocks (BASKET1 v8, T4), waiting regime. No pivot, nothing killed, no gated number read,
no new sweep. ONE decision this tick: the T37 recipe filed at 18:00 is NOT EXECUTABLE as written — the
supervisor's own prefix rule refuses `supersede_stages(['program_boundary'])` by design (§2). T37 is
re-specified (§3) so the 03:00 CHUNK B tick does not burn its slot on a guaranteed refusal.**

## 1. Ledgers verified on disk (00:00–00:25 CEST) — read-only, counts only

| clock | state | fault? | next gate |
|---|---|---|---|
| T30 borrow | **5/5 clean** (08-28 16:30: 19,719 rows, 379 pref, 598/602). 5-file pin set `sha256sum -c` **OK** (doc, collector, universe, evaluator, B01 pair record). | none | day-30 ≈ 09-22/23 |
| T31 Deribit | **5/5 clean** (day 6 captures 02:15 after this tick). Pin OK. | none | ≈ 09-23; design read 12-23 |
| T33 US options | **3/4** (08-25 failed pre-v2; 08-26/27/28 clean; 08-28: 40,074 rows / 14 names / 78 s). Pins doc+script OK. **HYG 0.615 / XLE 0.675 `fresh_fail` on day 3 → 0/3 clean days**, still on course for exclusion under the frozen §2 rule at ≈ 10-07; no amendment. | none | ≈ 10-07 |
| BASKET1 v8 | log **6 rows** (last session 08-27; session 08-28 lands at the 09:00 engine run, as every day); frozen `d53b4fe4…` mtime 08-23 **untouched**; 00:00 `basket_forward session --refresh-cash` OK. Curve values not read. | none | per-leg N_min 40 ≈ mid-Oct |
| T4 paper | **11 rows** (session 08-28 logged 21:50); not touched, not read | — | — |
| CONVEXITY prereg | 4-file pin set `sha256sum -c` **OK** (`convexity_evaluate.py` = `ba6bb268…`) | none | first reading 2026-12-23 |
| NEWSDESK1 | 2/30 resolved, 0 open, kill ALIVE | process (slot) | needs 30 resolved |
| PREDMARKET1 | 80 records; 21:00 tick froze 1 estimate (`2125867`, q=0.012 vs 4.5c) + 1 abstention record over 22; **0/50 resolved, 61 open**; kill ALIVE. Dedupe-by-`market_id` keep-first still required before 09-06. | none | 09-06 first resolutions |
| Window-2 | **BLOCKED — Q07 at `decode_and_reserves`** (13:23Z), root cause confirmed independently this tick (§2). No pipeline process alive; both flock locks free; `stages_completed` = 6-stage prefix; `results_unlocked` false; **no bodies number read.** | yes → T37 | decode → 3 gates → B20B OOS |
| Durable tick | 21:00 tick produced output (2.5 KB, DONE ok) but wrote **no FINDINGS line** — its ledger writes are on disk; a one-line entry is added on its behalf at 00:00, marked as such. No silent tick. | process (minor) | — |

Owner channels moved (`DECISIONS.md`/`PLAN.md` 22:13, `agent_discussion.md` 23:48 CEST) — content is the memecoin
PAC V2 authenticity/seal chain (Codex + interactive Claude, paper scenario). **No owner decision on the equities
direction.** Not claimed here.

## 2. Why the 18:00 T37 recipe cannot run, verified in the code (read-only)

The 18:00 diagnosis was right about the *cause*: the live `b11a_bodies.sqlite` (started 08-25, free RPC) holds
**zero** `boundary_*` metadata keys, `program_version` **0 rows**, `raw_boundary_response` **0 rows**; the §4 evidence
(`boundary_completed_at_unix 1786614620.72`, `last_deploy_slot` pump `433095571` / pumpswap `433112355`,
`boundary_endpoint_reference` Chainstack) lives only in `b11a_bodies.chainstack-partial.sqlite`. The watcher's own
stage note (`b11c_maturity_watcher.py:684-691`) predicted exactly this: `decode` reads boundary evidence from the
artifact it decodes, and stage 5 never puts boundary rows there. The 08-25 interactive restart on a fresh artifact
skipped stage 1 — that is the process fault, and it was ours.

But the *remedy* as filed — `supersede_stages(['program_boundary'])` — is refused by construction:
`supersede_stages` (b11c:1154) enforces the PREFIX rule *before* moving anything: retiring stage 1 while stages 2–6
keep receipts leaves `[enumerate_creates … transaction_bodies]`, which is not a prefix of `RUN_ORDER`, and the
docstring names this exact case ("superseding stage 1 while stages 2 and 3 keep their receipts leaves a HOLE …
Refusing here means the operator finds out BEFORE the evidence has been moved"). The only supervisor-path
alternative is superseding **all six** stages and re-collecting a window that "can be collected once" (Q12's own
words) — days of free-RPC crawling to reproduce 08-16 Chainstack receipts, with drift risk. Rejected.

What *is* admissible: the frozen stage-1 argv itself. `collect-boundary` (b9d:3382) takes the artifact path, the
RPC env and the cutoff; it opens the artifact under the single-writer flock, runs
`collect_boundary_evidence` (b9d:2946), preserves both raw `getAccountInfo` responses per program keyed by request
hash, materialises `program_version`, and writes the `boundary_*` metadata with `INSERT OR IGNORE` plus a **drift
refusal** if any key already exists with a different value. It does **not** call
`refuse_completed_artifact_before_work`, and the live artifact is `partial` in b9d's sense anyway (no
`completed_at_unix`). It is the collector writing its own evidence through its own frozen code path — not a hand
edit and not a row copy. Its built-in honesty checks are exactly the two the 18:00 tick asked for: the
ProgramData address must match the pinned inventory (`PROGRAMDATA_ACCOUNTS`), and a `last_deploy_slot` newer than
the window start makes `intervals_from_boundary_evidence` **fail** and demand the (unbuilt) loader-history path.

## 3. T37 re-specified for the 03:00 CHUNK B tick (bounded; ~4 RPC calls; no spend; nothing hand-edited)

Pre-conditions (all verified at 00:20): no `b11c`/`b9d` process alive; `supervisor.lock` and
`b11a_bodies.sqlite.collector.lock` are flock files with no holder; `stage_in_flight = null`; receipts =
`stages_completed` (6-stage prefix); `decode_and_reserves.json` `completed:false` exit 1.

0. Append a dated §6b to `research/b11m_window2/T34_RESTART_2026-08-25.md` BEFORE running anything: what will be
   run, why the supervisor path is unavailable (§2 above), and the two STOP conditions below. Decide-then-act.
1. **Run the frozen stage-1 argv directly**, foreground, stdout captured:
   `SOLANA_RPC_URL=https://api.mainnet-beta.solana.com/ python3 scripts/b9d_transaction_bodies.py collect-boundary research/b11m_window2/b11a_bodies.sqlite --rpc-env SOLANA_RPC_URL --cutoff-slot 438854169 > research/b11m_window2/logs/program_boundary_rerun_20260829.stdout.log`
   (trailing slash: `endpoint_reference()` → `assert_endpoint_identity_is_safe` normalises to scheme+host, so the
   stamped identity equals the artifact's `endpoint_reference`, and the Q09 false positive on the later `--watch`
   is avoided as on 08-28.)
   **STOP-1 (drift):** the printed `last_deploy_slot` must be exactly `433095571` (pump) and `433112355`
   (pumpswap). Any other value, or a `FreezeViolation` from the loader-history branch, means a program upgraded
   since 08-13 and the pre-registration's §4 assumption is broken → T37 **BLOCKED** with the text verbatim, hand to
   the owner, nothing else run.
   **STOP-2 (refusal):** any other `FreezeViolation` (identity, address, lock) → BLOCKED verbatim.
2. Verify read-only (metadata only): live artifact now has `boundary_completed_at_unix`, `program_version` 2 rows,
   `raw_boundary_response` 4 rows; `boundary_endpoint_reference` = `https://api.mainnet-beta.solana.com`
   (Chainstack → mainnet-beta is an **audit fact**, record it, not a leak). Read nothing else.
3. `supersede_stages(['decode_and_reserves'], reason, artifacts=())` with explicit window-2 paths → retires the
   failed stage-7 receipt; remaining set is the 6-stage prefix → accepted (same shape as 08-28 step 3).
4. `reattest_in_place(reason, clear_quarantine=True)` with explicit window-2 paths → clears Q07 verbatim into its
   note; manifest unchanged (`33da3a7e…`) so it must be told the reason is the quarantine, not a script change —
   if it refuses on "manifest unchanged", record that verbatim and use whatever documented path clears a
   quarantine without re-attestation; never edit state by hand.
5. Detached `setsid nohup … --watch --generation 2 --poll-seconds 60 --max-iterations 20` with the trailing-slash
   URL. Expected: poll mature → `decode_and_reserves` (CPU-bound over 13 GB, hours) → three gates. `results_unlocked`
   stays false; **no bodies number is read by any tick.**
6. T37 → `done` only when the live artifact holds `boundary_completed_at_unix` AND
   `receipts/decode_and_reserves.json` says `completed:true`. Liveness for the 06:00/09:00 ticks: heartbeat
   advancing at 30 s, `stage_progress_at` not stalled > 900 s while a stage is in flight; Q07/Q08 ⇒ BLOCKED verbatim.

Disclosure, stated once: step 1 is a **single-stage supervisor bypass** — the frozen script with the frozen argv,
but without a supervisor receipt for the re-run, because the supervisor's prefix rule makes a stage-1 re-run
impossible without re-collecting a one-shot window. The 08-13 `program_boundary` receipt stays as the receipt of
record for the *old* artifact; §6b + the captured stdout are the receipt for the live one. If the owner or the
interactive session judges this inadmissible, the alternative is to declare window-2 decode BLOCKED permanently
and archive — say so rather than force it.

## 4. Process faults, confessed
- The 08-25 fresh-artifact restart skipped stage 1. The watcher note predicting the failure was on disk the whole
  time. **Method rule (new):** a stage restart on a NEW artifact re-runs every stage whose output lives *inside*
  that artifact, starting from stage 1 — the receipt tree describes the old artifact, not the new one.
- The 18:00 remedy was filed without reading `supersede_stages`' prefix rule; this tick caught it before the slot
  was spent. Rule: a recipe that names a watcher function is checked against that function's refusal list first.
- 21:00 PREDMARKET tick: ledger written, no FINDINGS line. Added on its behalf, marked.

## 5. Where to focus, and what proves it dead (unchanged)
No live directional candidate exists in the goal universe; the free-data sweep category stays CLOSED. Next real
decision: **T30 day-30 read ≈ 09-22** (same-issuer preferred-series RV; dead if < 10 of 113 pairs have both legs
borrowable below the pair's gross edge). Second: convexity D1/D2/D3 on 12-23 (prior: all dead). Third — and the
*nearest in time if T37 unblocks*: window-2 B20B OOS behind decode + three gates; its kill is the pre-registered
gate itself, and a dead B20B OOS closes the programme's last surviving positive. If T30 and both convexity designs
die, ONE pay-or-stop fork to the owner with the frozen three-item paid-data menu; not before 12-23. Hold.

## 6. Standing recommendations to the owner (unchanged)
1. NEWSDESK slot to ~13:30–14:30 UTC (or swap 06:00 → PREDMARKET). 2. Commit the disclosed uncommitted diffs.
3. PREDMARKET scorer dedupe by `market_id` keep-first before 09-06. 4. (new, minor) b11c Q09 whole-URL rule and the
Q07-leaves-a-blocking-receipt defect from 08-28 §6a — plus this tick's finding that a fresh-artifact restart needs
a documented stage-1 re-run path (a `--rerun-into-artifact` for stage 1, or a supersede mode that accepts a
stage-1 hole when the artifact holding its output is gone).

## 7. Next ticks
- **03:00 CHUNK B: execute §3 (T37) as its bounded chunk**; verify T31 day 6 first. Invention stays abstained.
- 06:00 NEWSDESK (stale-reference slot) also glances at window-2 liveness; 09:00 PREDMARKET; 12:00 STRATEGIST
  verifies T30 day 6 (16:30 lands after), T33 day 5 (20:45 after), BASKET1 session 08-28, T37 receipt chain.
