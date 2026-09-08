# STRATEGIST decision note — 2026-09-02 00:00 CEST (durable supervisor, CHUNK A)

## State of play (verified read-only this tick)

- **Disk / incident follow-through:** 12G free (98%). The 09-01 disk crisis is RESOLVED at the
  root cause, by Codex, and confirmed here in code and crontab: `pac_lws_feed.py:600` now
  constructs `b15i.RawLog` with the frozen retention parameters (DECISIONS.md 09-01 ~19:15:
  512 MiB self-rotation + 45 GiB reserve authority); the emergency `*/30` rotation cron is
  removed (both t4 crontab lines untouched); `raw_frames.jsonl` is 0 B since 18:30 and the
  burn (38 GB/day at peak) has stopped. **Owner/Codex decision on record: the LWS feed is
  deliberately STOPPED and must not restart until disk headroom and the exposed old credential
  are repaired.** Restarting it is not a supervisor action.
- **Collectors all clean:** T30 borrow-forward **9/9 clean** through 09-01 (day-9 verify done
  here; 5-file pin `sha256sum -c` OK; ledger at `research/data/borrow_forward/`); T31 Deribit
  **9/9 clean** (day 10 lands 02:15 today; pin OK); T33 US options **09-01 clean** (HYG/XLE
  fresh-frac still <0.70 → exclusion track ≈ 10-07). BASKET1 **8 rows**, frozen
  `BASKET_FORWARD_FROZEN.json` mtime 08-23 **untouched**, curve not read. t4 path untouched.
- **U4 still absent.** DECISIONS.md moved 09-01 19:15 with substantial entries (PAC_LWS stop,
  VIRALITY_GATE_B_V1 retirement with pinned hashes, PAC_SCALP_LL NO-GO reaffirmed at 130
  checks, ARM-2 ledger-integrity suspension) — but **no window-2 unlock entry**. Window-2
  `state=all_stages_complete`, `results_unlocked=false`. **T38 stays BLOCKED-on-U4
  (attended)**; the packet is now ~4 days old.
- **Auto-stamps reconstructed (both 09-01 ticks healthy, FINDINGS line only was skipped):**
  18:00 CHUNK C = judged abstention on a **genuinely live feed** (60 events, 42 fresh <24 h
  during US RTH — evidence against the "always stale" half of T42; SEC_8K still unproven);
  21:00 CHUNK D = disciplined abstention (pull was 2028 longshots + already-frozen
  geopolitical markets; 66 open, 0 resolved).

## Decision (one, hygiene + ordering — no evidence read early)

1. **T44 closed `done`** on verified Codex delivery + the owner stop-decision (verification
   above). The residual pac_v22 feed_events audit is moot while the feed is stopped and
   belongs to an owner-gated restart checklist, which would be a NEW task.
2. **T43 promoted to priority 1** — it is now the only pending build with a hard deadline:
   the first predmarket close is **2026-09-06 (four days)**, and 66 frozen estimates are worth
   nothing if resolution scoring isn't wired when they close. The next CHUNK D ticks (09:00 /
   21:00) must build it: resolve+score FIRST in every tick, market_id keep-first dedupe,
   early-closure fetch-by-id (2125867; Duma 2046123/25/26 pull-coverage gap), `--limit ≥ 3000`.
   Kill-condition (unchanged from T43's filing): <10 of the ~25 mid-Oct closers scored by
   10-15 despite T43 done → re-open the sunset question with that evidence.

## Direction (unchanged, converged)

Nearest read **T38 (attended, hours, $0)** — needs only an owner U4 entry. Then **T30 ≈ 09-22**
(the pay-or-stop fork date if DEAD per the 08-30 re-dating; PREFRV `--start` fires mechanically
if ALIVE — design T39 + runner T40 both pinned). T31 ≈ 09-23; convexity 09-22/10-07/12-23 in
the background at $0. Free-data sweep category CLOSED; the waiting regime has nothing left to
construct except T43 (deadline-bound) and T42 (evidence now says the feed is intermittently
live; the open question is SEC_8K + intraday coverage, next weekday CHUNK C).

Open surface after this tick: **T38 (blocked on U4, prio 1) + T43 (pending, prio 1, deadline
09-06) + T42 (pending, prio 3)**.

Guardrails honored: no commit, no orders, no spend, no wallet, basket untouched, t4 untouched,
no `borrow_forward/extract` read, no forward number read early, LWS feed left stopped.
