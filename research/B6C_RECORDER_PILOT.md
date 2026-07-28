# B6-lite — Recorder Pilot Results

Run: 2026-07-27, approximately 12:30–12:50 UTC. Author: Claude.
Recorder: `scripts/recorder.py`, implementing frozen `docs/schema/RAW_CAPTURE_SPEC.md` v0.2.
Data root: `/home/anont/pump-capture` (internal ext4, gitignored).

Read-only against the network. No keys, no signing, no transactions.

## What was validated

| Spec element | Result |
|---|---|
| CRC32C-framed append-only segments | 3 segments written, all scan **clean** |
| Sealed segments + SHA-256 sidecar | all sealed, integrity **OK** on re-verification |
| `session` as append-only open/close events | 6 rows |
| `gap` register | 3 rows, all correctly attributed |
| `clock_sample` | 10 rows, `sync_state` from OS |
| `frame_index` / `slot_observation` | 48 rows each |
| **I3 crash recovery** | **passes — see below** |

### I3 crash recovery, tested by deliberate corruption

The recorder was hard-killed (`os._exit`) after writing a deliberate 4-byte torn tail, with no
segment seal and no session close record. On restart it:

1. detected the session opened with no close,
2. scanned the active segment and stopped at the first invalid record,
3. truncated the 4 torn bytes and fsynced,
4. sealed the segment and wrote its SHA-256 sidecar,
5. appended a session close with `close_reason = crash`,
6. **emitted a `gap` row with `detected_by = crash_recovery`.**

```
[recovery] session deb290977245: sealed at seq 4, truncated 4 torn bytes, gap recorded
```

The recovered segment subsequently verifies clean with a matching SHA-256. I3 required that a
crash lose at most a bounded, *detectable* tail and that recovery record a gap rather than
silently truncate. Both hold.

## F26 — Polling captures only ~14% of the chain (verified fact, decisive)

| Run | Blocks captured | Rate |
|---|---:|---|
| 90 s run | 36 | 0.39 blocks/s |
| 20 s run | 7 | 0.34 blocks/s |

Solana produces ~2.5 slots/s. **The poller sustains ~0.35 blocks/s — roughly 14% coverage**, and
the deficit was correctly recorded as two `slot_discontinuity` gaps rather than hidden.

This settles the provider question empirically: **polling `getBlock` on a public RPC cannot be a
recorder.** It would silently miss ~86% of the chain, and the missing slots are not random — they
correlate with whichever blocks are large and slow to serve, i.e. the busiest ones. A Geyser
subscription is a hard requirement for any real capture, not an optimization.

Its value was never throughput: it validated framing, sealing, integrity, sessions, the gap
register, clock sampling, crash recovery, and compression, all of which transfer unchanged to a
Geyser source.

## F27 — Compression is 10–27×, not the assumed 4× (verified fact; revises F20)

Measured **per segment**, not on a concatenation, so cross-segment redundancy is not inflating it:

| Segment | Raw | zlib-6 | lzma-1 |
|---|---:|---:|---:|
| 000…004 | 7.83 MB | 11.04× | 29.03× |
| 000…006 | 13.03 MB | 11.61× | 28.10× |
| 000…035 | 33.92 MB | 9.51× | 26.22× |
| **Total** | **54.78 MB** | **10.15×** | **27.03×** |

Measured payload: **1,168.7 KB/block** across 48 blocks → **241 GB/day raw** at full slot rate.

| Codec | GB/day | 72 h pilot | 166 GB holds |
|---|---:|---:|---:|
| none | 241 | 723 GB | 0.7 days |
| zlib-6 | 23.7 | **71 GB** | 7.0 days |
| lzma-1 | 8.9 | **27 GB** | 18.6 days |

**This overturns F20.** F20 concluded that a 72-hour full-fidelity pilot needed 220–280 GB and did
not fit. Two things changed: compression is 2.5–7× better than the 4× assumed, and 114 GB of disk
was freed. At lzma-1 the full-fidelity 72-hour pilot costs **~27 GB** — comfortably affordable —
and 166 GB holds nearly three weeks.

**Tiering is therefore no longer forced by capacity.** It remains defensible for other reasons
(bounded replay window, cheap long-horizon queries), but the argument that full raw capture is
unaffordable is withdrawn.

Caveat: JSON compresses exceptionally well. Geyser protobuf starts smaller but compresses less,
so the *ratio* will drop even though absolute volume should improve. The ratio must be re-measured
against a real Geyser frame before retention constants are fixed.

## Limitations

- Total capture is ~2 minutes across three short runs. Pump traffic is non-stationary (F9), and
  1,168 KB/block is one snapshot.
- Everything measured is JSON from an RPC, not Geyser protobuf. Both the volume and the
  compression ratio will change.
- Duty cycle was not measured: runs were bounded and deliberate, so no sleep/suspend or
  long-run stability was exercised.
- `lzma-1` costs materially more CPU than zlib. At 2.5 blocks/s sustained this needs a throughput
  check before adoption; it was not measured here.
- No `dead_or_skipped` slot was encountered, so that path is written but unexercised.

## Follow-ups

1. Re-measure volume and compression against a real Geyser frame before fixing retention.
2. Benchmark lzma-1 compression throughput at sustained capture rate.
3. Exercise a long run to measure real duty cycle including host sleep.
4. Revisit the tiering decision now that capacity no longer forces it.

## Subsequent audit correction

See `research/B6D_RECORDER_AUDIT_AND_COMPRESSION.md`. The pilot's crash-recovery mechanism remains
valid, but the first implementation wrote the crash gap's `first_missing_hint` one sequence too
low and could persist a custom credential-bearing RPC URL. Both are fixed and regression-tested.
More importantly, the polling adapter's filtered JSON is reconstructed, not byte-identical RPC
wire data. Therefore this pilot validates recorder mechanics and approximate JSON compression;
raw-frame fidelity remains untested until a Geyser adapter stores received protobuf bytes.
