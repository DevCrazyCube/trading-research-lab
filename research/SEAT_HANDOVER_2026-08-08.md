# Seat handover — what the `codex` seat did on 2026-08-07, for whoever holds it next

**Read `research/SEAT_HANDOVER_2026-08-07.md` first.** It explains the seat, the protocol and the
three delivery traps, and **none of that has changed**. This file is the delta: one day's work, the
things that turned out to be false, and what is open.

Written by the Claude session that occupied the seat on 2026-08-07. Codex's limit resets 14:03 on
2026-08-08, so the seat may return to Codex.

## The single most important thing on this page

**`research/b11a` is being written by a live watcher, right now, and it has run for over 2 days 20
hours without a quarantine.** Do not touch it, its artifacts, or `scripts/b11c_maturity_watcher.py`,
`scripts/b11a_window_freeze.py`, `scripts/rpc_http_identity.py`, `scripts/recorder.py`. That
constraint is unchanged and was honoured all day.

It is at **stage 2 of 9**, `enumerate_creates`, ~97% through 203,601 slots. **Stage 1 is the only
one complete.** Seven stages remain after this one.

## What was wrong about the watcher, and is now corrected in DECISIONS

The GO decision (handoff 162) estimated the whole nine-stage run at ~36.5 hours and 1.34 TB, from a
probe measuring 6.53 MB and 1,527 ms per `getBlock`. Measured against the running job at 95%:

| | estimate | measured |
|---|---|---|
| per block | 6.53 MB | **11.5 MB** average |
| per call | 1,527 ms | **4,800 ms** |
| this stage | 21.6 h | **~69 h** |
| transfer, this stage | — | **~2.3 TB** |

**It is bandwidth-bound, and neither estimate modelled bandwidth at all.** Sustained throughput is
9.4 MB/s over `wlan0`; there is no wired interface. At ~17 MB blocks that ceiling is 0.55 blocks/s
against an observed 0.56. Zero retries, backoffs or 429s in 65 hours of stage log — the provider is
not limiting anything, the connection is simply full. Adding workers cannot help.

**The confirmation arrived by accident later the same day**: the link halved to 4.33 MB/s and the
slot rate halved to 1,500/h in lockstep, ratios 0.46 and 0.50, with block size steady. If the run
were latency- or CPU-bound those would not track. The collection rate is a direct readout of the
WiFi link.

**Disk is not at risk and never was**: 98 MB kept after ~2.2 TB transferred, ~0.5 KB per slot,
against 128 GB free. The transfer figure matters only for a metered connection.

**No replacement whole-run figure is offered**, deliberately. Extrapolating one stage's overrun
across seven differently-shaped stages would repeat the error being corrected. What is known: days
rather than hours, bounded by the link.

## What was built (27 commits)

- **Slice D — three strategy preregistrations** (`B19B`/`B19C`/`B19D`), frozen and hash-pinned by
  `scripts/b19_preregistration_register.py`. Committed **alone** at `f72019e` before the register, so
  the history shows they preceded the code. B19d's candidate signals are all **booleans** from the
  frozen B11b contract, which makes threshold-tuning impossible to express rather than merely
  forbidden.
- **G7 — mutation evidence made reproducible** (`scripts/mutation_sweep.py`). 131 of 270 commits
  cited mutation numbers that lived in deleted scratchpads. Now **8 declared sweeps, 168/170 killed,
  2 declared survivors**, all re-runnable from the repository.
- **Slice E — the emergency-state owner** (`b20a`) and its **operator surface** (`b20b`), built under
  explicit owner authorization. `kill_switch_engaged` and `emergency_state` were mandatory inputs to
  `b12a.assert_health` that **nothing produced**; they now have exactly one owner.
- **B21a** — a reading note on two trading subreddits, every figure labelled an unverified
  third-party claim.
- The **audit log backlog** committed at `111a625` (handoffs 132–209). **The per-handoff `audit:`
  convention should resume from 210.**

## Four things that turned out to be false, and how

Each was recorded rather than quietly fixed, and each is now a standing lesson in the gap map's
section 7. They are the most useful part of this page.

1. **"They are the same list."** recorder.py's five Geyser-phase gates were claimed to be b18a's
   seven `U_NOT_INSTRUMENTED` fields. The overlap is **empty**. Both seats verified the *counts* —
   five and seven — and neither compared the *items*. **Five is not seven**; the arithmetic alone
   should have stopped it. → *a count is not a comparison.*
2. **Q03 recorded as unreachable.** True of one branch, false of the other, which the mutation
   framework's own staging reaches on every run. → *unreachability proved of one branch is not
   unreachability of the code*, and an unreachable-by-design note is a **stopping** claim nobody
   re-tests.
3. **`killed_by` could not answer the question it was built for.** It records the first failure
   under `-x`, not the responsible guard. Renamed `first_failing_test`.
4. **Tests that broke because the property they assert held.** `LiveCollectionIsUnreachableTests`
   calls `tracked_files(ROOT)`; a staged tree has no `.git` — which is *why* it cannot reach the live
   collection — so the tests could not run. → *a skip is a check that cannot fire wearing different
   clothes*; assert where the skip must **not** fire.

## Two traps beyond the three in the previous handover

- **Dashboard ownership is enforced by nothing.** No tool in either seat's toolchain reads the flag.
  This seat *took* ownership and still tripped the other seat's sweep. Coordinate by message, and
  **hold working-tree edits while any sweep runs** — a sweep's central claim is that the tree did not
  move, and it cannot tell a colleague's edit from its own escape.
- **A sweep run against uncommitted work produces a number describing code nobody can check out.**
  Caught once, mid-run, only because the other seat volunteered that they had work in flight. If you
  run sweeps, run them against a clean `HEAD`.

## What is open

- **b12b reading the b20a snapshot** — the last G6 step, a read path. Taken by the claude seat at
  time of writing; confirm before starting. Neither the console nor `b12b_preview_server.py` may gain
  a write path.
- **Four `U_NOT_INSTRUMENTED` fields remain** — `retry_policy_id`, `slippage_limit_tokens`, `route`,
  `provider_region_declared`. Left deliberately: filling them would name a policy, a limit and a
  route that do not exist. **Do not fill them to reduce a count.**
- **76 staged-tree failures across 9 test files** need untracked artifacts (~864 MB). Deferred, and
  the symlink that would expose them is argued **against** in G7: tracked-only staging is exactly why
  a staged tree cannot reach the live `research/b11a`.
- **Slice D's three studies have not been run**, and B19d may only be evaluated on a window nobody
  has read.
- **Nothing consumes the emergency state yet** beyond its own CLI.

## What none of this establishes

No strategy, no edge, no result. No wallet, key, signer, transaction, signing, submission or spend
exists anywhere in this repository, and slice E did not change that. 168 killed mutants show that
168 guards are load-bearing; they do not show that any guard is right.
