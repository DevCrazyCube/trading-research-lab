# B11a maturity watcher and collection supervisor — v1.0.0

`scripts/b11c_maturity_watcher.py`. Waits for the frozen B11a observation cutoff to finalize, then
runs the frozen collection stages once each, unattended.

## Before maturity: one method, one commitment

`getSlot` at `finalized`, through B11a's own preflight allowlist. Nothing else is reachable — not
because a denylist forbids it but because the allowlist contains one method and every other is
refused for not being in it.

**Finalized, not processed or confirmed.** A slot that can be rolled back is not a cutoff, and a
window opened on a slot that later disappears was opened on nothing. Maturity is `tip >= cutoff`
exactly; one slot early is early.

Default poll: **300 s**. The cutoff does not move, so polling faster buys nothing and only adds load.

## Verified before anything starts, and again on every resume

- the preregistration's file **and** canonical hashes (B11a's own check — the file digest catches
  any edit, the canonical digest catches one that changed the meaning);
- the document against the burned-range register, via `assert_matches_preregistration`;
- git ancestry: the preregistration commit must be an ancestor of HEAD;
- a **manifest of 11 files** — every stage script, both pinned IDLs, and both preregistration
  files. A stage script that changed is a stage that does something else now.

## Stage order

`program_boundary` → `enumerate_creates` → `signature_inventory` → `transaction_bodies` →
`decode_and_reserves` → `reserve_coverage_gate` → `failure_coverage_gate` → `simulator_replay_gate`

**The A2 probe runs first.** An upgrade boundary is a property of the program rather than of the
window, so it costs no composition — and if version coverage cannot be proven there is nothing worth
collecting.

**Results stages are unreachable.** One enforcement, and it is B11a's own `assert_stage_permitted`
with `results_unlocked=False`, which already encodes both maturity and the results lock. A local
copy of either rule would be a second check that fires only when the first already has.
`FORBIDDEN_STAGES` remains as a published declaration and is asserted to equal the pipeline's own
results stages — a declaration that drifted from what it describes reads like a guarantee and
guarantees nothing.

## Stage wiring — repaired, and `launch_ready_for_collection: true`

B9c and B9d read exactly four columns from a B9a-shaped source — `mint`, `bonding_curve`,
`launch_slot`, `is_mayhem_mode`. All four are identity or regime facts, and all four are in B7d's
`create_event`. Established by reading their SQL, not assumed.

`build_cohort` is therefore a **local stage** (offline, no network, no evidence produced) that runs
`b11d_cohort_adapter` between the enumeration and its consumers. See `B11D_COHORT_ADAPTER` in
`research/B11C_WATCHER_AND_COHORT.md` for what it refuses to do.

`b9d run` now takes `--b9c`/`--b9a`, and b9d distinguishes **burned** from **fresh** sources: the
pinned hashes and frozen counts describe the burned corpus and are not applied to a fresh window,
which must verify itself as a cohort artifact instead. **A mixed burned/fresh pair is refused** —
that collects one window's signatures under another window's identity map, and neither artifact
shows a sign of it afterwards.

The `Q11_stage_wiring_unresolved` guard remains for the next stage that is not wired, and is tested
against an injected unresolved command.

## Liveness — a stored state is not a running process

`--status` used to read the state file and ask nothing else, so a supervisor that died on Tuesday
would still have reported `waiting_for_maturity` on Friday. It now reports **three independent
signals** and publishes the stored value separately as `reported_state`:

| signal | why |
| --- | --- |
| the pid is running **this** watcher | matched on `scripts/b11c_maturity_watcher.py` **and** `--watch`, because a test runner invoked on `tests/test_b11c_maturity_watcher.py` carries the module name in its own argv |
| the instance lock is actually held | acquiring it means nobody does |
| the heartbeat is fresh | within three poll intervals; one missed poll is a slow endpoint, three is a process that is not polling |

All three agreeing is `alive`; none is `dead`; anything in between is `stale`, because signals that
disagree are never "running normally". The watcher writes its **own** pidfile under the lock and
removes it on a clean exit, so a leftover pidfile means a crash.

`archive_run` moves a superseded run's state and pidfile aside — never erases — and refuses to
archive a run with completed stage receipts.

## Durability

- **Single instance** via `flock`, not a pidfile: a pidfile survives `kill -9` and locks nobody out.
- **Atomic state**: written to a temporary path and renamed. A half-written state file is not a
  state.
- **One receipt per stage**, written atomically after it finishes. A stage with a receipt is never
  rerun.
- **Completed stages must be a true PREFIX** of the run order. `["simulator_replay_gate"]` alone is
  in run order and is not a prefix: it means every earlier stage was skipped.
- **A stage interrupted mid-flight quarantines**, never resumes. A partial artifact is not a
  checkpoint, and this process cannot tell an interrupted run from a corrupted one.

## Failure handling

Bounded retries with exponential backoff (cap 120 s) for transport hiccups — timeouts, resets,
429/502/503/504. Anything else quarantines **immediately**: retrying past a `401` would be guessing
about why it failed. Thirteen quarantine codes, `Q01`–`Q13`.

## Secrets and composition

**The endpoint is recorded as `scheme://host`.** The configured URL carries its key in the query
string, so anything recording a URL records a secret.

Every durable write passes through a scan against the live environment secrets, and **a match is
fatal rather than redacted** — a redaction that fails silently looks exactly like one that worked.

**Composition never leaves.** A leak is a *number keyed by a word describing the window*
(`{"curves": 1234}`), not the word appearing anywhere: the stage `enumerate_creates` is a name, and
a scan that fired on the pipeline's own vocabulary would be turned off within a week. Counts may
exist inside sealed artifacts and their own logs; the supervisor publishes stage state and pass/fail.

## Commands

```
python scripts/b11c_maturity_watcher.py --dry-run   # offline plan, no network
python scripts/b11c_maturity_watcher.py --verify    # offline verification only
python scripts/b11c_maturity_watcher.py --status    # liveness + redacted operator status
python scripts/b11c_maturity_watcher.py --watch     # the watcher
```

Launched detached via `scripts/b11c_watcher_entrypoint.sh`, run inside a `tmux` session named
`b11a-watcher`. The entrypoint sources `.env` **itself** rather than taking the URL as an argument
or via `tmux new-session -e`: anything on a command line lands in a process argv, where `ps` shows
it to every user on the box.

Note that a tmux session inherits the **server's** environment, not the launching client's — so a
session started against an already-running server sees none of what the client exported. That is
why the entrypoint sources the file rather than relying on inheritance.

## Not covered

- B10b paths, B10c labels, B11b evaluation, or any outcome stage. **U4 and U5 remain a later
  explicit human decision after collection.**
- Any unlock of results or publication of composition.
