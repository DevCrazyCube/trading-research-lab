# B6b — Storage Hardware Audit

Run: 2026-07-27, approximately 12:05 UTC. Author: Claude.
Read-only inspection (`df`, `lsblk`, `findmnt`). **The USB device was not mounted, written to,
formatted, or modified in any way.**

Purpose: verify the actual storage available before sizing the B6 retention tiers, because the
tier sizes are load-bearing (F20) and were about to be set from stated rather than measured
capacity.

## Measured

| Device | Size | Filesystem | Mounted | Notes |
|---|---:|---|---|---|
| `nvme0n1p2` (internal) | 467 GB total | ext4 | `/` | **392 GB used, 52 GB available, 89% full** |
| `sda1` (external) | **115.2 GB** (123.7 GB decimal) | **exFAT** | **not mounted** | model reports `FLASH DRIVE` |
| `sda2` | 32 MB | vfat | not mounted | — |

Only one USB disk is attached.

## F22 — Three assumptions behind the retention plan are wrong (verified fact)

1. **The external drive is 115 GB, not 200 GB.** It reports 123.7 GB decimal, which is how a
   "128 GB" flash drive is typically marketed. Either a different drive was intended, or the
   200 GB figure was from memory. Worth resolving before tiers are sized.

2. **The internal disk has only 52 GB free and is 89% full.** This was not part of the stated
   budget and is the real bottleneck. A root filesystem should not be driven near 100%, so
   realistically **~25–30 GB** of internal space is usable for capture without risking the OS.

3. **Realistic total usable is ≈ 140 GB, not 300 GB** (≈25–30 GB internal + ≈110 GB external).

**Consequence: F20's conclusion is unchanged and strengthened.** At the measured ~94 GB/day,
a 72-hour full-fidelity pilot still needs 220–280 GB and still does not fit. **Tiered retention
remains mandatory.**

## F23 — exFAT is unsuitable for the Tier 1 raw-capture path (verified fact)

`docs/schema/RAW_CAPTURE_SPEC.md` invariant **I3** requires that a crash lose at most a *bounded,
detectable* tail, recovered by truncating at the first invalid record and emitting a `gap` row.
That guarantee assumes the filesystem itself survives the crash and that `fsync` means what it says.

exFAT has **no journaling**. An interrupted write can corrupt directory structures, not merely the
tail of the active segment — which turns a bounded, detectable loss into an unbounded, possibly
undetectable one. That is precisely the failure mode I3 exists to prevent.

**Recommendation:** hot append-only writes go to the internal ext4 filesystem. The external drive
holds Tier 2 — sealed, SHA-256-checksummed, immutable segments, written once. Its per-segment
checksum sidecar then makes corruption *detectable* even on exFAT, which is the property that
matters for a cold archive. Reformatting the drive to ext4 would be better still, but it is
destructive and is the owner's decision, not ours.

## F24 — A USB flash drive is not a viable continuous-write target (working hypothesis, strong)

The model string reports `FLASH DRIVE`. (`lsblk` shows `ROTA=1`, but that is the USB bridge
failing to report rotational status, not evidence of a spinning disk.)

Continuous capture at ~94 GB/day sustains roughly **1.1 MB/s indefinitely — about 2.8 TB written
per month**. Consumer USB flash drives have limited program/erase endurance and no meaningful
wear-levelling guarantees. Sustained capture would plausibly wear the device out, and its failure
mode is typically silent corruption or abrupt read-only remount rather than a clean error.

This reinforces F23's split: **write hot data to internal NVMe, move sealed segments to USB.**

## F25 — Removable storage is a new gap cause (proposal, not a spec edit)

The `gap.detected_by` enum in frozen spec v0.2 covers `seq_discontinuity`, `slot_discontinuity`,
`session_down`, `heartbeat_timeout`, `crash_recovery`, and `host_sleep`. A USB drive being
unplugged, or auto-unmounted on sleep, is a distinct and — on this hardware — likely operational
event that none of those describe.

Proposing `storage_detached` as an additional cause. **Not editing the frozen spec**: per Seq 12
the freeze lifts on a concrete invariant failure from B6, and this is a predicted one, not an
observed one. If the pilot's crash/restart test reproduces it, that is the trigger.

## Revised tier proposal

| Tier | Location | Size | Contents |
|---|---|---:|---|
| 1 — hot rolling raw | internal ext4 | ~25 GB | byte-identical frames, aged out |
| 2 — permanent events | external exFAT | ~100 GB | sealed, checksummed, decoded events |

At ~2 GB/day for decoded events (F21), Tier 2 holds **well over a month** and grows slowly.
Tier 1 at ~25 GB holds roughly **one day** of raw frames uncompressed, or ~3–4 days at a 4×
compression ratio — a ratio the pilot must measure rather than assume.

The 60/40 GB split proposed in Seq 18 is withdrawn; it assumed internal space that does not exist.

## Limitations

- Free space is a snapshot; the internal disk is in active use for other work.
- The external drive is unmounted, so its existing contents and free space are unknown. It may
  not be empty.
- Compression ratios remain assumed, not measured.
