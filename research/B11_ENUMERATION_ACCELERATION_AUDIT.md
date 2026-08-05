# B11 stage-2 acceleration audit — evidence and verdict

**Question (handoff 178):** can the running `enumerate_creates` be sped up safely, rather than
accepting ~0.83 slots/s?

**Verdict: NO-GO for mid-stage acceleration.** The data layer is provably safe to resume at a
different worker count. The gain is real but modest and saturates at 8 workers, and collecting it
requires five deliberate weakenings of the safety envelope on a one-shot window. The evidence for
both halves is below. Nothing was stopped, edited, signalled or copied: the live run
(pid 3315033, child 3315135) was untouched throughout.

## What is safe — proven offline, `tests/test_b7d_worker_count_resume.py`, 11 tests

B7d's architecture makes worker count irrelevant to the evidence, for three reasons that are driven
rather than argued:

1. **Resume is a set difference.** `pending = [slot for slot in range(...) if slot not in completed]`
   where `completed` is every `slot_scan` row already `retrieved` or `skipped`. A stored slot is
   never refetched; a missing slot always is.
2. **There is exactly one writer.** Results are consumed from `executor.map` on the main thread and
   `store_result` is called there, so raising the worker count adds fetch concurrency and *no* write
   concurrency. There is no SQLite contention to assess — the question does not arise.
3. **The export is canonically ordered**: `ORDER BY slot, transaction_index,
   outer_instruction_index, inner_instruction_index`. Its bytes are a function of content, not of
   insertion order.

Driven results:

| claim | how it was shown |
|---|---|
| identical evidence after interrupt-and-resume at a different worker count | interrupt at 4, resume at 16: `slot_scan`, `create_event`, `decode_error` digests and the **exported JSONL bytes** all match an uninterrupted 4-worker run |
| survives repeated interruption at varying widths | kills at 4, 16 and 2 workers in sequence, then completion at 16 — same digests, same export bytes |
| no duplicates, no misses | every slot present exactly once, in order, across a resume |
| canonical ordering preserved | export coordinates sorted and unique after a resume |
| worker count is not pinned in the database | metadata pins `start_slot`, `end_slot_exclusive`, `program_id`, `idl_sha256` — **not** workers, so a differing worker count is not a metadata mismatch |
| the window still cannot move | changing `--end-slot` on resume is refused with `metadata mismatch` |
| a partial run cannot look finished | `export_jsonl` refuses an incomplete window, so no truncated export can be produced |

One real cost, measured: **an interruption discards the blocks fetched ahead of storage.** Workers run
ahead of the single consumer, so a kill loses whatever is in flight — about `workers` blocks, roughly
67 MB at 8 workers. Trivial in itself, and it scales with the width being interrupted.

## What the speed-up actually is — live benchmark, 120 preserved slots per configuration

Range **433,900,000–433,900,119**, inside the burned B8b/B9d corpus. The B11a fresh window was
asserted against and never touched. Same slots for every configuration, through the actual patched
transport. Total probe: **360 requests, 3.0 GB**.

| workers | wall | slots/s | median latency | p90 | max | MB/slot | peak RSS | 429/5xx |
|---|---|---|---|---|---|---|---|---|
| 4 | 242.5 s | **0.495** | 2,482 ms | 17,427 ms | 70,812 ms | 8.32 | 372 MB | none |
| 8 | 144.6 s | **0.830** | 3,044 ms | 17,157 ms | 82,855 ms | 8.32 | 582 MB | none |
| 16 | 159.2 s | **0.754** | 7,270 ms | 21,127 ms | 83,232 ms | 8.32 | 1,013 MB | none |

**Content digest identical across all three** (`ba133071…`), which confirms the offline proof against
the real endpoint.

Four things follow:

- **8 workers is ~1.68× faster than 4.** That is the whole prize.
- **16 workers is SLOWER than 8** and nearly triples median latency. Throughput saturates and then
  regresses, so 32 was not attempted: it would cost more memory to go further backwards.
- **The 50-RPS Growth limit is not the constraint.** Observed rate was 0.5–0.83 requests/s, about
  **1.7%** of the budget, with zero 429s, zero 5xx and zero retries across 360 requests. The binding
  constraints are per-block latency with a very heavy tail (p90 17–21 s, max 83 s) and an 8.32 MB
  payload per slot.
- **Memory is the resource that bites.** The live child already holds ~1.0 GB at 4 workers; 8 would
  raise that, and 16 measured 1,013 MB in the benchmark process alone against 6.6 GB available.

**Caveats stated rather than controlled.** The benchmark ran *contended* with the live enumeration, so
absolute throughput understates a solo run — the live rate measured 0.600 slots/s while the benchmark
was competing, against 0.83 uncontended. The relative comparison holds because all three
configurations were contended alike. Cache warmth is uncontrolled and biases the result *in favour*
of the later, higher-worker configurations.

## The arithmetic

At the time of audit: **57,381 of 203,601 slots stored (28.2%)**, 146,220 remaining, ~1.22 TB of
transfer still to come.

| scenario | remaining |
|---|---|
| continue at 4 workers, 0.83 slots/s | **48.9 h** |
| 8 workers at the measured 1.68×, 1.39 slots/s | **29.2 h** |
| 8 workers, conservative 1.10 slots/s | 36.9 h |

So the prize is **roughly 12–20 hours**, and the 28.2% already collected is *not* lost either way —
resume keeps it.

## Why it is a NO-GO anyway

Acceleration is not a parameter that can be turned. The stage command in `b11c.stage_commands()`
passes **no `--workers` flag**, so b7d uses its default of 4. Changing it means editing either b11c or
b7d — both **manifest-pinned**. Collecting the 12–20 hours therefore requires, in order:

1. killing a healthy stage that is making steady progress;
2. hand-clearing `stage_in_flight`, which exists precisely to make `assert_resume_is_safe` quarantine
   Q08 on an interrupted stage — the mechanism would have to be defeated deliberately;
3. editing a manifest-pinned file;
4. re-attesting the manifest while a **stage-1 receipt exists**, which `archive_run` correctly
   refuses, so the only existing path is `incident_quarantine` — and that is the wrong tool: it marks
   evidence INVALIDATED and removes files, which is not what a healthy run needs;
5. re-running the verification cycle and relaunching.

The risk is not data loss — that is disproven above. The risk is **procedural**: five manual overrides
of the mechanisms that protect a window which cannot be recollected. This project has already lost two
runs to defects in exactly this machinery (a transient URLError misclassified as fatal, and a path
credential written into a collected artifact). Spending five deliberate overrides to save 40% of one
stage's wall-clock, on evidence that is already 28% collected and progressing without incident, is a
poor trade.

**Q08 is conservative rather than necessary for this stage, and that is worth recording.** B7d's own
resume is a set difference and its export refuses an incomplete window, so for stage 2 specifically a
partial artifact *is* a legitimate checkpoint. Q08's blanket rule is right across the pipeline as a
whole and stricter than stage 2 requires. Relaxing it is a supervisor design decision for after
collection, not something to reach for mid-run.

## If Codex decides to accelerate anyway

The minimum-risk shape, stated so the decision is informed rather than improvised:

- **8 workers, never 16.** 16 is measurably worse.
- Add `--workers 8` to the stage command rather than changing b7d's default, so the change is visible
  in the receipt's argv and in the stage-command tests.
- Do **not** use `incident_quarantine`: no evidence is bad. What is needed instead is a narrow,
  explicitly-authorised path that clears `stage_in_flight` while preserving receipts and the stage-2
  database, with a test proving the stage-2 DB is untouched.
- **Back up the stage-2 database before touching anything** — `sqlite3 .backup` against a read-only
  connection, never a file copy of an open WAL database.
- **Rollback:** restore the backup, restore `stage_in_flight`, revert the manifest-pinned edit,
  re-attest. Recoverable at every step because the b7d DB is the only irreplaceable artifact and it is
  resumable by construction.
- **Budget the overhead honestly:** stop, back up 400 MB+, edit, test, mutation-sweep, re-attest,
  relaunch and re-verify is realistically 1–2 hours of attended work, against a 12–20 hour saving.

## What was not done

No live process was stopped, signalled, edited or copied. No live file under `research/b11a` was
written; the two progress reads used read-only SQLite connections, which do not block the writer. The
fresh window was never queried — every benchmark slot was asserted to be inside the burned corpus and
outside the window. No manifest-pinned code, stage command, cadence, watcher, B15 artifact, model or
signing path was modified. No composition or outcome figure was inspected or published: the only
window-derived number quoted here is scan *progress*, which is geometry rather than content.
