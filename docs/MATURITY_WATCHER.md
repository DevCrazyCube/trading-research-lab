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

## Stage wiring — two stages are NOT ready

`--dry-run` reports `launch_ready_for_collection: false`. Two stages cannot be pointed at the
isolated `research/b11a/` directory through their own interfaces:

| stage | why |
| --- | --- |
| `signature_inventory` | `--source`/`--database` are explicit, but the script expects a **B9a-shaped** cohort schema while this window's population comes from the B7d enumerator. The compatibility has never been demonstrated |
| `transaction_bodies` | `b9d run` reads its population from the module-level `B9C_PATH`/`B9A_PATH` constants and **accepts no override**, so it would collect this window against the **burned** corpus's inventory. Only `verify`, `decode` and `verify-artifact` take `--b9c`/`--b9a` |

At maturity the watcher runs what it can prove — the A2 probe and the create enumeration — and then
**quarantines** with `Q11_stage_wiring_unresolved`. Running an unresolved stage would either collect
into the burned corpus's paths or read the burned corpus as this window's population, and both
destroy an artifact that cannot be recollected. Resolving this needs a separate, reviewed change to
the collection scripts.

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
python scripts/b11c_maturity_watcher.py --status    # redacted operator status
python scripts/b11c_maturity_watcher.py --watch     # the watcher
```

## Not covered

- B10b paths, B10c labels, B11b evaluation, or any outcome stage. **U4 and U5 remain a later
  explicit human decision after collection.**
- Any unlock of results or publication of composition.
