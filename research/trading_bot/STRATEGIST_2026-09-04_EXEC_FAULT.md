# STRATEGIST — 2026-09-04 (CHUNK A) — the tick harness is an unaudited input surface, and this tick is the proof

**Status of this tick: DEGRADED. No ledger was verified. Do not read this document as a clean bill.**

Paper/research only. No orders, no spend, no wallet, no broker. No commit. No BASKET1 leg and no
re-freeze. `t4` untouched. No gate, prereg, pin or kill-condition moved.

---

## 1. What happened

This supervisor tick could not execute **any** shell command.

Observed, in order:

| command | result |
|---|---|
| `date +%H` (+ other commands producing stdout) | exit 1, no output |
| `echo hi` | exit 1, no output |
| `echo hi` with the sandbox disabled | exit 1, no output |
| `pwd; echo hi` | exit 1, no output |
| `true` | reported success, no output |
| `date +%H > /tmp/tick_hour.txt 2>&1; true` | reported success — **file created, contents empty** |
| `printf 'HELLO' > /tmp/tick_hour.txt; true` | reported success — **file still empty** |

The last two rows are the diagnostic ones. A command that writes a literal string to a file and
reports success, leaving the file empty, is not a command that ran and failed. **Nothing executed.**
The shell surface reports `exit 0` for a no-op and `exit 1` for anything else, and in neither case
does work happen. Read/Write/Edit against the filesystem worked normally throughout, which is how
this document exists.

**Scope is UNKNOWN and is not being guessed at.** I cannot distinguish (a) a harness/sandbox-level
fault confined to this one headless session from (b) a host-level `/bin/sh` fault that would also be
breaking the crontab — and the second case is the one that matters, because the collector crons
(T30, T31, T33, T45, window-2 watchdogs) are the clocks the entire converged direction is waiting on.
Determining which is a task for an actor with a working shell. It is filed as **T50** below.

## 2. The strategist point, which is not about a broken shell

For nine ticks this programme has been running **T48**: audit the data path of every live instrument,
on the finding that a green *decision-path* selftest says nothing about the *input* surface. Nine
instruments, nine faults, and the earned method rule was: *an input surface is honest in proportion to
the number of places it is willing to refuse; readers refuse nowhere, which is why they hold seven of
the nine faults.*

T48 audited every instrument the tick reads from. **It never audited the tick itself.**

The tick harness is an input surface with exactly the property the thesis predicts is dangerous:

- It is a **reader**, not an archival collector. It has no provenance record, no hash chain, and
  nothing ever diffs its output against a source — its output goes straight into a judgement, which
  is the precise shape of faults #2, #3, #4, #7, #8 and #9.
- It **refuses nowhere.** A tick that cannot execute a single command is, under the current design,
  still perfectly able to append a confident, well-formed, entirely fictional line to `FINDINGS.md`.
  Nothing in the pipeline would catch it. The one existing guard — `durable_tick.sh`'s `[AUTO-STAMP]`
  stub, added 2026-08-29 — fires when a tick writes *nothing*, and is therefore blind to exactly the
  failure mode that matters: a tick that writes something.
- The failure is **silent by construction, and biased toward the flattering answer.** In the waiting
  regime, the honest report and the fabricated report look identical: "all ledgers verified, no
  faults." That sentence has been written on eleven consecutive CHUNK A ticks. It is the single most
  repeated claim in this file, and until today nothing tested whether the actor writing it could
  actually run the verifications it names.

This is fault class #10, one level up from the other nine: **the audit harness is subject to the
thesis the audit exists to enforce.** It is also, unlike the previous nine, a fault that can
manufacture evidence rather than merely degrade it.

I want to be exact about what is and is not being claimed. There is **no evidence that any previous
tick fabricated anything** — the prior write-ups carry specific reproducible numbers (row counts,
sha256s, slot ranges) of a kind that a non-executing tick could not invent. The claim is narrower and
structural: *nothing in the design would have stopped it*, and today establishes that the precondition
occurs in practice.

## 3. Decision

**Direction: UNCHANGED and CONVERGED.** Hold the line to the 09-22 / 09-23 reads. This tick changes
no gate, promotes no strategy, and opens no lane. The free-data sweep category stays CLOSED; BASKET1
legs and re-freezes, new free cross-section sweeps and new forward lanes all remain forbidden.

Three decisions, all bounded:

**(a) NOT VERIFIED is recorded as this tick's ledger status.** T30, T31, T33, T45, BASKET1, T4,
NEWSDESK, PREDMARKET, convexity pins and `results_unlocked` were **not** checked this tick. Not
"checked and clean" — not checked. A degraded tick that reports clean is worth less than no tick.

**(b) T50 filed, priority 1.** The next actor with a working shell establishes whether the host cron
path is affected, *before* anything else. This outranks T48/T49 because if the host shell is down,
every clock the direction depends on is accruing silent missing days into gate denominators that are
frozen and cannot be re-cut without owner authorisation — the same class as the T31 08-24 off-clock
day, but potentially many days wide and on every collector at once.

**(c) New standing method rule, effective now:**

> **A tick must prove it can execute before it is allowed to report.** Any tick that reports on a
> ledger it did not successfully query must say NOT VERIFIED and name the reason. An unexecuted
> verification and a passed verification must never produce the same sentence.

The mechanical form of this belongs in `durable_tick.sh` (a pre-flight canary command whose output is
checked, with the result stamped into the tick's own FINDINGS line), but `durable_tick.sh` is the
harness that runs these ticks and I cannot test an edit to it from inside a session with no shell.
**Editing it blind would be the worse fault** — the rule is recorded here and in T50; the wiring is
T50's deliverable, by an actor that can run the selftest.

## 4. What this tick did NOT do, and why

- **Did not run CHUNK B / C / D.** Their assigned work (`newsdesk read|spot|propose|status`,
  `predmarket pull|propose|status`) is CLI-only and is unreachable without a shell. The rotation's
  hour could not be read either (`date +%H` was among the first casualties), so the documented
  fallback — CHUNK A — applies.
- **Did not run T48 tranche 6 (MEME ARENA).** The last instrument in the series needs live ledger
  queries. It stays open; T48 does not close this tick.
- **Did not start T49** (the pay-or-stop packet). It is a writing task and *is* reachable with file
  tools alone, which makes it tempting. Declined deliberately: T49 is due 09-20, it is assigned to the
  idle CHUNK B invention capacity, and starting it here would mean a degraded tick quietly doing a
  second chunk's work instead of reporting its own failure. One bounded chunk, honestly reported.
- **Did not edit any collector, rule, prereg, pin or scoring path.** Blind edits with no ability to run
  a selftest are exactly how a fix becomes a fault.
- **Did not claim the host cron is broken.** It may well be fine. Unknown is recorded as unknown.

## 5. Nearest reads (unchanged)

| what | when | state |
|---|---|---|
| **T38** window-2 OOS (B19L/B20B) | hours, $0 | **BLOCKED on owner U4** — 4th consecutive tick with `DECISIONS.md` untouched. Still the nearest real read by weeks. |
| T30 borrow day-30 gate | ~09-22 | running (unverified this tick); pay-or-stop fork fires here if it dies |
| T31 Deribit day-30 | ~09-23 | running (unverified); score on-clock days only, 08-24 is 11h10m off its clock |
| T45 K1 | ~09-23 | running (unverified); K1 is the live risk and it is a world rate |
| PREDMARKET first settlements | 09-06, 09-20 | 66 open estimates; calibration is the only live question |
| T33 / convexity | 10-07, 12-23 | $0 background |

**Open surface:** T50 (new, prio 1) · T38 (blocked-attended) · T48 (MEME ARENA, then closes) ·
T49 (by 09-20) · T46 + T47 (standing duties).

**Next step, single most important:** the next tick with a working shell runs T50's Step 1 — confirm
the collector crons produced their 2026-09-04 rows — before doing anything else.
