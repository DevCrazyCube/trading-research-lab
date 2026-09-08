# Birth-stream reconnect repair

Author: Codex. Date: 2026-09-08 UTC. Status: **decision implemented; NO_TRADE**.
Owner authorization: fix the stopped recorder and start it again.

## Verified failure

The original eight-hour session stopped at 18:07:13 UTC, about 225.66 seconds after
starting, with `WebSocketProtocolException: ('Invalid close opcode %r', 1006)`.
The old code treated any transport exception as terminal and had no reconnect loop.
It was not a storage-capacity stop or a creation-decoder failure. The exception does
not establish which remote service or intermediary caused the broken connection.

The original SQLite/log files remain unchanged: 37,939 raw frames, 24 creation
observations (23 successful transactions, one failed), one transport issue, zero
pending raw frames. Exact raw/derived replay still passes after this repair. The
original 8,502-frame pilot also still replays exactly. The old implementation and
verifier are preserved in `birth_stream_v1_source_20260908/`; hashes match their
original session/review pins. No old data is relabeled as continuous or recovered.

## Decision: bounded reconnects, explicit gaps

`scripts/birth_stream.py` now writes schema `birth-stream-v2`:

- Retry socket/protocol/connection failures and rejected subscriptions, using a
  capped 1, 2, 4, 8, 16, 30-second backoff. Only an actual decoded notification resets
  the backoff, not a successful socket connection or acknowledgement alone.
- Reconnect after 30 seconds without a received data frame. A receive timeout near
  the fixed run deadline does not renew the run. Socket cleanup errors cannot mask
  recovery; underlying socket shutdown is attempted separately.
- Each connection attempt has its own epoch, subscription acknowledgement and
  sequence range. Every v2 raw hash binds its connection epoch. A provider reusing
  the same subscription number does not merge connections.
- Transport outages record their boundary, last observed slot, detection time and
  resumed receipt/slot, when available. Resumption is the first decoded notification,
  not the new subscription acknowledgement. Consecutive unsuccessful attempts remain
  inside one still-open outage. Every gap stays `UNKNOWN_UNREPAIRED` even after reconnect.
- Raw frames are still committed before decoding. Duplicate observations across
  connections are retained and reported, never counted as independent launches by
  assumption. A new subscription does not backdate receipts or recover missing events.
- Storage, persistence and non-transport failures remain fatal and visible; they are
  not retried as network failures. Capacity stop remains terminal. Duration and storage
  bounds belong to the whole session, not to each connection. No process supervisor
  restarts fatal errors or resets the eight-hour limit.

The verifier reads both v1 and v2. For v2 it checks epoch accounting, per-frame epoch
hashes, acknowledgements, explicit outage coverage, resumption receipts and exact
derived replay. Deleting a gap or presenting an acknowledgement as resumption fails.
Matching/replaying captured data still does not prove discovery recall or executable
returns. This repair supersedes the old contract's **no reconnect** operational detail,
not its original strategy/preregistration or any performance gate.

## Why eight hours, and what can run faster

**Decision:** eight hours is a configurable pilot capture budget, not computation time
or a minimum imposed by the recorder. The proposed birth-origin observer uses six
hours of preceding creations; the pilot allowed six hours of history plus two hours
of subsequent observation. The observer is NOT wired to this live collector yet, and
eight elapsed hours is not a promise of a signal, complete history, or a trading result.

The collector processes observations as they arrive and exposes health immediately.
Historical replay can run faster than real time. Seeding from separately enumerated
history might reduce a later observer's warmup, but needs complete canonical evidence
and honest availability times; it is not implemented here and cannot replace fresh
forward outcome observations. Reconnect gaps cannot count as six hours of continuous
coverage. No lookback or preregistration was shortened to produce a faster result.

## Restart and health

**Verified operational snapshot:** v2 started at 2026-09-08 18:22:48.931 UTC in
tmux session `birth-create-v2-20260908-1823`, pane process 258843. The first health
check saw 1,183 frames, three creation observations, no issues, and a decoded
notification about 0.019 seconds old. This is startup proof, not guaranteed future
uptime. The session manifest pins the code actually started, duration 28,800 seconds,
8 GiB capture budget, and planned stop 2026-09-09 02:22:48.931 UTC. The 16 GiB
free-space reserve also remains enforced. Bounds are approximate by in-flight frame,
SQLite overhead and bounded connection/close waits. No files are deleted.

Output: `birth_stream_forward_v2_20260908T1823.sqlite` and `.log`.
The old session is closed and preserved, not resumed into this new database.
The downtime between sessions is not filled or silently bridged.

Immediate read-only status:

```sh
python -m scripts.birth_stream --status research/midcap/birth_stream_forward_v2_20260908T1823.sqlite
```

Health distinguishes recent decoded notifications, stale/connecting state, receiving
after unrepaired gaps, and a closed session's stop reason. A live PID or subscription
acknowledgement alone is not healthy data. `notification_age_seconds` and advancing
frame counts are the evidence, not this static note.

**Follow-up live check at 18:27:13 UTC:** 36,380 frames, 70 creation observations,
one connection epoch, no issues/gaps, most recent decoded notification about 0.004
seconds old, session still open. This is more than four minutes after restart,
beyond the previous run's 225.66-second failure point. A real reconnect had not been
needed at this snapshot; automatic recovery is proven by the deterministic runtime
tests below, not misrepresented as already observed on the restarted public feed.

**Subsequent verified REAL recovery at 18:28:22–18:28:24 UTC:** the public connection
raised the same `WebSocketProtocolException: ('Invalid close opcode %r', 1006)`.
V2 closed epoch 1 at sequence 46,759, resubscribed (ack sequence 46,760) and received
the first decoded notification of epoch 2 at sequence 46,761 without operator action.
Last pre-error receipt: 18:28:22.692820747; first post-reconnect notification:
18:28:24.090886460 (1.398 seconds later). At 18:28:36 UTC, status showed 48,596
frames, 83 creation observations, two connection epochs, one recorded unrepaired gap,
and fresh data. This directly demonstrates recovery from the original failure.

The recorded slot boundary is 445406023 → 445406470, a 447-slot jump. Therefore the
short receipt-time reconnect interval does NOT bound missing chain history. Buffered
or delayed delivery is a possible explanation, not diagnosed here. No missed-create
count or coverage fraction can be inferred from these endpoints alone. The entire
gap remains UNKNOWN_UNREPAIRED; source head lag/independent census remains an open gate.

## Tests and source pins

```sh
python -m unittest scripts.test_birth_origin scripts.test_memecoin_information_audit scripts.test_birth_stream scripts.test_birth_stream_verify scripts.test_birth_stream_reconnect
```

**Verified engineering result:** 62 tests pass. New deterministic runtime attacks cover
1006 recovery, clean close, close-method failure, changed/reused subscription IDs,
repeated connect failures with exact backoff/deadline, silent sockets, subscription
errors, fatal storage failure, capacity stop, interruption, deleted gaps and stale/
ack-only health. These are not profitability tests or a network uptime benchmark.

- Running recorder SHA-256:
  `b08d7a0dbbd3a63040d8df75875941a24e29455382b4e75ac6ee75839670e675`.
- Verifier SHA-256:
  `eb31398be06e959fa98670099b8edd9ac4a179cb48ade803669f1a3c0eb4740c`.
- Original formation prereg remains unchanged, SHA-256
  `1b25538f988a561dd9a8234cd9b1397b1287a1ece4adfbadeaa75e2f7aaf5141`.

Primary interface sources accessed 2026-09-08 UTC:
[websocket-client connection/timeout examples](https://websocket-client.readthedocs.io/en/latest/examples.html)
and [Solana logsSubscribe](https://solana.com/docs/rpc/websocket/logssubscribe).
These document interfaces, not service uptime, creation completeness or trading edges.
