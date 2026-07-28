# Raw Capture Specification (minimal, B6-enabling)

Version 0.3 — 2026-07-27. Author: Claude; invariant review: Codex. Status: frozen for B6 pilot.

Scope: the **minimum** format needed to start the 72-hour local capture pilot (B6). Deliberately
not a full canonical-event schema. Per `agent_discussion.md` Seq 10, schema refinement freezes
after this document is reviewed once, until B0 and B6 produce evidence.

## Principles

1. **Capture first, decode later.** A wrong decoder is replayable; a lost frame is not.
2. **No interpretation at capture time.** Nothing in this spec understands Pump, curves, or prices.
3. **Silence is a lie.** Downtime, unknown frames, and torn writes are recorded as data.
4. **Storage-engine neutral.** Defined as logical relations plus a plain-file segment layout.
   Local-only operation (`DECISIONS.md`) means no database is required to start.

## Non-goals for v0.1

Decoded events, canonical chain state, reserves, features, decisions, provider selection,
compression tuning, and retention policy. Retention is set by the pilot's measured bytes-per-slot.

## Storage layout

```
<root>/
  segments/<recorder_id>/<session_id>/<seq_lo>-<seq_hi>.seg   append-only frame data
  segments/<recorder_id>/<session_id>/<seq_lo>-<seq_hi>.seg.sha256
  meta/sessions.jsonl        append-only, one record per session open/close
  meta/gaps.jsonl            append-only
  meta/clock_samples.jsonl   append-only
  index/frame_index.jsonl    append-only, derivable from segments
  index/slot_observation.jsonl  append-only, derivable from segments
```

Only `segments/` is irreplaceable. Everything under `index/` is rebuildable from segments and may
be deleted and regenerated; `meta/` is **not** rebuildable and must be treated as primary data.

### Segment record framing

Each record, little-endian:

```
u32  record_len          length of payload_bytes
u32  header_len          length of header_json
u64  seq_in_session
u32  record_crc32c       little-endian CRC32C over header_json || payload_bytes
     header_json         UTF-8 JSON, header_len bytes  (see raw_frame minus payload)
     payload_bytes       opaque, record_len bytes
```

A record is valid only if the complete 20-byte fixed header plus `header_len + record_len` bytes
are present and the CRC matches.
The first invalid record terminates the segment; see Crash recovery.

An active segment has no trusted SHA-256 sidecar. On clean roll or crash recovery, truncate any
invalid tail, fsync the segment, write and fsync its SHA-256 sidecar, and never append to the sealed
segment again. Start a new segment after recovery.

## Relations

### `raw_frame` — immutable, the only irreplaceable relation

| Field | Type | Notes |
|---|---|---|
| `recorder_id` | string (ULID) | stable per recorder process instance |
| `session_id` | string (ULID) | one provider connection |
| `seq_in_session` | u64 | monotonic from 0, no gaps within a session |
| `provider_seq` | u64? | upstream sequence when the provider exposes one; never synthesize it |
| `provider_message_id` | string? | upstream message/heartbeat identity when available |
| `received_at_mono_ns` | u64 | monotonic clock, for interval arithmetic |
| `received_at_wall_ns` | u64 | UTC wall clock, for chain correlation |
| `payload` | bytes | provider message, **byte-identical, never rewritten** |
| `payload_encoding` | enum | `protobuf`, `json`, `bincode`, `unknown` |
| `payload_schema_version` | string | provider-declared proto/schema version, or `unknown` |
| `provider_kind` | enum | vendor-neutral category, e.g. `geyser_grpc`, `rpc_ws`, `rpc_http` |
| `subscription_id` | string | which subscription produced this frame |

`seq_in_session` proves local recorder ordering and idempotency; it cannot detect a message the
provider never delivered. Upstream loss detection uses `provider_seq`, provider heartbeat identity,
or, when unavailable, the weaker slot/session discontinuity checks. Provider capability must be
recorded in the subscription specification.

Two clocks are mandatory. Wall clock alone is insufficient: an NTP step silently corrupts every
latency measurement derived from it, and the corruption is undetectable after the fact.

### `frame_index` — derived, every field nullable

| Field | Type |
|---|---|
| `recorder_id`, `session_id`, `seq_in_session` | key, see below |
| `message_kind` | enum: `transaction`, `account_update`, `slot_status`, `block_meta`, `heartbeat`, `error`, `unknown` |
| `slot` | u64? |
| `commitment` | enum? `processed`, `confirmed`, `finalized` |
| `signature` | bytes(64)? |

An unparseable frame is stored with `message_kind = unknown` and **counted**, never dropped.
A rising `unknown` rate is an alarm, not noise.

### `session` — not rebuildable

`session` is materialized from append-only `session_event` rows (`open` or `close`); an existing
JSONL record is never updated. Fields are `session_id`, `recorder_id`, `provider_kind`, `endpoint_ref` (opaque local handle — **never a URL
containing credentials, never a token**), `subscription_spec` (JSON) and `subscription_spec_sha256`,
`opened_at_wall_ns`, `opened_at_mono_ns`, `closed_at_wall_ns?`, `closed_at_mono_ns?`,
`close_reason` (`clean`, `error`, `timeout`, `remote_close`, `recorder_shutdown`, `crash`, `unknown`),
`frames_received` u64.

An open session with no close record and no live process means `crash` — see recovery.

### `gap` — not rebuildable

`gap_id`, `session_id`, `detected_by` (`seq_discontinuity`, `slot_discontinuity`, `session_down`,
`heartbeat_timeout`, `crash_recovery`, `host_sleep`, `log_truncated`), `first_missing_hint` u64?,
`last_missing_hint` u64?, `detected_at_wall_ns`, `note` string?.

`host_sleep` is included because operation is local: a closed laptop lid is a normal, frequent gap.
`log_truncated` requires an explicit provider truncation marker; event absence alone is not one.

### `slot_observation` — derived

`recorder_id`, `session_id`, `seq_in_session` (provenance back to the frame), `slot` u64,
`parent_slot` u64?, `status` (`processed`, `confirmed`, `finalized`, `dead_or_skipped`),
`observed_at_mono_ns`, `observed_at_wall_ns`.

Repeated observations of the same slot at different statuses are **expected and retained**.
Orphan classification is derived later from these rows and is never decided at capture time.

### `clock_sample` — not rebuildable

`recorder_id`, `clock_domain_id` (stable for one OS boot/process monotonic-clock domain),
`sampled_at_wall_ns`, `sampled_at_mono_ns`, `sync_state` (`synchronized`, `unsynchronized`,
`unknown`), `est_offset_ns` i64?, `est_error_ns` u64?, `source` (`ntp`, `ptp`, `os_report`).

Any window where `sync_state != synchronized` marks every latency derived from it as suspect.

## Invariants (the predeclared review criteria)

**I1 — Idempotency key.** The unique key for a frame and for everything derived from it is
`(recorder_id, session_id, seq_in_session)`. Re-ingesting a segment is a no-op.
`(event_key, source_id, commitment)` **must not** be used: a source can legitimately re-report the
same event at the same commitment after a reconnect, and collapsing those destroys reconnect
evidence.

**I2 — Late-bound references.** No relation here holds a foreign key to a canonical chain event.
The observation→canonical link is resolved by a later reconciliation pass and is nullable.
Enforcing it at write time would either block ingestion of an observation whose canonical event has
not arrived — coupling ingestion to chain ordering, which the canonical-ordering rule forbids — or
force a fabricated placeholder parent.

**I3 — Crash recovery writes a gap.** On startup, for each session with no close event:
truncate the active segment at the first invalid record, seal it, append a session close event with
`close_reason = crash`, and **emit a `gap` row with `detected_by = crash_recovery`**. Set
`first_missing_hint = last_valid_seq + 1` when a valid record exists (otherwise null) and leave
`last_missing_hint = null`, because the unseen tail length is unknowable. Truncating silently is
forbidden: it produces a file that looks complete and is not.

**I4 — Compaction is parent-agnostic.** No compaction, dedup, or GC job may use "has no canonical
parent" as a deletion criterion. Parentless observations are the orphan record and cannot be
re-acquired. `never_canonical` is assigned only after the configured finality/reconciliation window
and is terminal unless an explicit audited correction record names the affected observation keys.
Enforced by a standing key-set test, not a count:

> Across a maintenance operation, the complete pre-operation set of protected observation keys
> `(recorder_id, session_id, seq_in_session)` classified `never_canonical` must be a subset of the
> post-operation set. Missing or altered protected keys fail the build. Newly created rows cannot
> mask deletion. An audited correction is tested separately and may not be performed by compaction.

Run it before and after every compaction, in CI and in the maintenance job itself.

## Pilot-blocking inputs still required

Local disk budget, expected host sleep/uptime behaviour, and a provider whose feed supplies
per-message sequence numbers or heartbeats (else `gap` detection degrades to slot-discontinuity
only) and slot-status transitions including dead/skipped slots (else `slot_observation` cannot
support orphan derivation). Both capability gaps are acceptable if recorded in `DOCUMENTATION.md`
rather than discovered later.
