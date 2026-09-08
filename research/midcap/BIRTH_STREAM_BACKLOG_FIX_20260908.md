# Birth-stream backlog: measured cause, batched repair, live comparison

Author: Codex. Date: 2026-09-08 UTC. Status: **verified engineering improvement; NO_TRADE**.
Owner authorized fixing the delayed feed and considering other money-making mechanisms.

## Diagnosis

**Verified fact:** v2 could report millisecond-old local receipts while consuming
old chain data. Its preserved creation observations range from 10.820 to 302.992
seconds between event timestamp and local receipt. Reconnecting restored liveness
but skipped unrepaired history; it did not solve the throughput bottleneck.

An offline, 2,000-frame profile on the SAME ext4 filesystem as production measured
12.546842 seconds, **159.40 frames/sec**. SQLite commit/context-exit calls alone used
5.570 seconds. The old loop committed raw, derived and notification state separately
for virtually every received frame, in the same thread that drained the socket.
Per-frame capacity checks and repeatedly constructing the same IDL event map also
contributed work. This profile identifies local costs; it does not attribute every
remote disconnect to the same cause.

The first two profiling runs accidentally used `/tmp`, which is tmpfs on this host.
Their ~980-frame/sec results are preserved but NOT accepted as disk-throughput evidence.
The corrected benchmark explicitly creates its ephemeral timing database under the
output parent on the production filesystem. All ephemeral benchmark databases are
discarded as timing fixtures, never treated as forward observations. No trading study
or old strategy grid was rerun.

Evidence: `birth_stream_profile_v2_disk_20260908/result.json` versus
`birth_stream_profile_v3_disk_20260908/result.json`. Both replay the exact same raw
prefix, SHA-256 `b79668429bbd35d1153b6631f8f2b9dd2734f9f7fcc43ee77beba9afce2e5c2e`.

## Repair and durability boundary

**Decision:** use `scripts/birth_stream_fast.py`, schema `birth-stream-v3-batched`.
The canonical observation/raw schemas and strict creation decoder remain compatible;
the change is receipt buffering and persistence, not a different token filter.

- Receive at most 32 frames, 1 MiB, or 50 ms into a small batch before flushing.
  Bounds can overshoot by one received frame and in-flight processing. Per-frame
  wall/monotonic clocks are captured immediately after receive, never at batch flush.
- Commit the entire raw batch with SQLite WAL **synchronous FULL before decoding any
  frame in it**. Decode from those saved bytes, then commit derived state separately.
  Cache the pinned event map for the connection/run. Capacity is checked at each
  flush; free-space checks occur on a bounded cadence. No old evidence is deleted.
- Preserve actual post-raw-commit and post-derived-commit clocks in `flush_batch`.
  A later decision consumer must join those availability clocks: original receipt
  alone does not prove decoded features were already available. No such trading
  consumer is activated here.
- A hard crash can lose the small, not-yet-committed receive batch. This is explicitly
  recorded in the manifest, not described as per-frame durable capture. No received
  data are decoded before raw durability. A failed raw transaction rolls back both
  disk and in-memory chain state; failed derived persistence leaves raw pending.
- Retain bounded reconnect/backoff, separate epochs and UNKNOWN_UNREPAIRED gap records.
  Drain received frames before marking a transport gap. Never treat a reconnect as
  recovering unseen history. Fatal storage/capacity failures remain terminal.
- The status tool exposes latest creation receipt lag and explicitly says chain-head
  freshness needs an RPC comparison; a fresh local receipt alone is not enough.

**Verified benchmark:** same prefix and filesystem, v3 took 2.309606 seconds,
**865.95 frames/sec**, approximately 5.43× the measured v2 rate. This is one bounded
engineering comparison, not a universal throughput guarantee or a profitability result.

SQLite's [WAL documentation](https://www.sqlite.org/wal.html) and
[synchronous pragma documentation](https://www.sqlite.org/pragma.html#pragma_synchronous)
explain the commit/durability tradeoff; accessed 2026-09-08. FULL durability was not
disabled to obtain the improvement.

## Live measurement, not just a benchmark

`scripts/birth_stream_headcheck.py` saves raw public `getSlot(finalized)` responses
and feed snapshots before/after each RPC request. The two feed snapshots bracket
the RPC observation rather than pretending their clocks were simultaneous. Source:
[Solana getSlot](https://solana.com/docs/rpc/http/getslot), accessed 2026-09-08.

**Verified eight-check comparison:** v2 lag brackets ranged from 22 to **990 slots**;
v3 from **-1 to 22 slots**. The -1 means the feed advanced during the request, not
that it predicted a future block. V2's lag reset on a reconnect and grew again; those
missing intervals remain explicit. V3 used one uninterrupted connection in this
comparison. Evidence: `birth_stream_head_comparison_20260908/`, including every raw
request/response and receipt, plus `result.json`.

**Verified after cutover:** three further checks had v3 before/after lag brackets
`[1,0]`, `[2,-1]`, `[0,0]` slots. Evidence:
`birth_stream_head_after_cutover_20260908/`. At the subsequent 369-creation snapshot,
v3 event-to-receipt delays ranged **10.535–22.782 seconds**, not minutes. This includes
finalized observation delay; it is not a claim to act at creation or before the
creator's same-transaction buy.

These checks use a public HTTP head and public WebSocket feed; provider independence
is NOT established. Near-head delivery does not establish complete discovery recall,
program deployment boundaries, accurate trade execution or any edge.

## Cutover, preservation and operation

V3 started at **2026-09-08 19:01:12.947 UTC** in tmux
`birth-create-v3-20260908-1901`, pane process **271662**. Output:
`birth_stream_forward_v3_20260908T1901.sqlite` and `.log`.
Duration 26,400 seconds, planned stop **2026-09-09 02:21:12.947 UTC**, slightly before
the prior run's planned end; repair did not buy another fresh eight-hour budget.
Limits remain 8 GiB capture capacity and 16 GiB free-space reserve. No watchdog
extends the deadline and no signing, treasury, orders or strategy activation exists.

The old v2 process 258843 was verified by exact command/session, then gracefully
interrupted only after the new feed passed live comparison. Its closed database
preserves **421,594 frames, 656 create observations, five unrepaired transport gaps**,
zero pending raw frames and stop reason INTERRUPTED. Its 645 distinct creation
transactions are not 656 independent births; duplicates/multiple observations remain.
No old SQLite/log file was overwritten. V2 source snapshots are preserved in
`birth_stream_v2_source_20260908/`. All earlier periods remain separate epochs/artifacts.

```sh
python -m scripts.birth_stream_fast --status research/midcap/birth_stream_forward_v3_20260908T1901.sqlite
```

## Verification

**Verified:** 76 engineering tests pass, including the reconnect attack suite through
both runtimes, raw-before-decode visibility from another database connection, batch
rollback, receipt preservation, and fatal derived-write failures. An earlier test
invocation displayed 87 because the imported base suite ran twice; the final module
avoids that duplication. Neither count is financial validation.

A separate 30-second real v3 validation capture closed with **7,482 frames and 12
creation observations** (11 successful, one failed), zero issues/pending/uncommitted
frames. All raw/derived records and batch/epoch clocks replay EXACT. It has 284
batches, at most 32 frames each. Maximum measured receipt-to-raw-commit delay was
69.836 ms; receipt-to-derived-commit delay 84.059 ms. These are observed maxima,
not an absolute crash-loss or future scheduling guarantee.

Evidence: `birth_stream_v3_validation_20260908.sqlite` and
`birth_stream_v3_validation_replay_20260908/result.json`. This validation checks
capture/replay, not a new independent transaction census or executable returns.

```sh
python -m unittest scripts.test_birth_origin scripts.test_memecoin_information_audit scripts.test_birth_stream scripts.test_birth_stream_verify scripts.test_birth_stream_reconnect scripts.test_birth_stream_fast
python -m scripts.birth_stream_verify --source research/midcap/birth_stream_v3_validation_20260908.sqlite --out /tmp/birth-v3-new-review
python -m scripts.birth_stream_benchmark --out research/midcap/new-disk-benchmark --rows 2000 --batched
```

Use NEW output paths. Benchmarking must remain on the production filesystem.

Pins: fast recorder `8befd9a54732c61bb3b860f559520bb9e7df94a3365e02b44dba72afc4843fd8`;
base recorder `02a10a92ffdab8c6f600c520e8c5b33d3b12b64903774f7fba99976125233e62`;
verifier `947bd2c975c9148f94507d11fe69c48d81a9927cd53e48a702739e114b36b7d3`.
The original formation preregistration remains unchanged at SHA-256
`1b25538f988a561dd9a8234cd9b1397b1287a1ece4adfbadeaa75e2f7aaf5141`.

**Open financial work:** `NEW_INFORMATION_CANDIDATES_20260908.md` separates one new
trading-information hypothesis, an explicitly different fee-service business option,
and conceptual rejections. No profitable trading strategy has been established.
