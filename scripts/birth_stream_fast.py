"""Bounded batched raw capture: per-frame receipt clocks, FULL durability before decode.

No price filter, strategy, signing or orders. Batch RAM is uncommitted until flush;
its bounds and commit clocks are explicit. Every transport gap remains unrepaired.
"""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import zlib

from scripts import birth_stream as BS
from scripts.birth_origin import Refused, canonical

BATCH_FRAMES = 32
BATCH_BYTES = 1024 ** 2
BATCH_SECONDS = 0.05


class Recorder(BS.Recorder):
    def __init__(self, path, *, max_bytes, duration_seconds=None):
        super().__init__(path, max_bytes=max_bytes, duration_seconds=duration_seconds)
        self.db.execute("CREATE TABLE flush_batch(first_sequence INTEGER PRIMARY KEY,last_sequence INTEGER NOT NULL,"
                        "raw_committed_unix_nanos INTEGER,derived_committed_unix_nanos INTEGER)")
        manifest = json.loads(self.db.execute("SELECT manifest_json FROM session").fetchone()[0])
        manifest.update(schema="birth-stream-v3-batched", batch_frames=BATCH_FRAMES,
                        batch_bytes=BATCH_BYTES, batch_seconds=BATCH_SECONDS,
                        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        base_recorder_sha256=hashlib.sha256(Path(BS.__file__).read_bytes()).hexdigest(),
                        durability="FULL raw batch commit BEFORE any decode; receipts remain individual",
                        uncommitted_loss_bound="up to one 32-frame/1-MiB/50-ms receive batch, plus one frame and in-flight work; no restart continuity claim")
        self.db.execute("UPDATE session SET manifest_json=?", (canonical(manifest).decode(),))
        self.db.commit()

    def append_batch(self, items):
        if not items:
            return []
        if not self.epoch:
            self.begin_connection()
        sequence, previous, wall_previous, mono_previous = self.sequence, self.previous, self.wall, self.mono
        start, sequences = sequence + 1, []
        with self.db:
            for raw, wall, mono in items:
                if len(raw) > BS.MAX_FRAME_BYTES:
                    raise Refused("frame size exceeds recorder bound")
                sequence += 1
                body = {"sequence": sequence, "received_unix_nanos": wall,
                        "received_monotonic_nanos": mono, "raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "raw_bytes": len(raw), "previous_sha256": previous, "connection_epoch": self.epoch}
                record_hash = hashlib.sha256(canonical(body)).hexdigest()
                self.db.execute("INSERT INTO raw_frame(sequence,received_unix_nanos,received_monotonic_nanos,"
                    "raw_sha256,raw_bytes,raw_zlib,previous_sha256,record_sha256,connection_epoch) VALUES(?,?,?,?,?,?,?,?,?)",
                    (sequence, wall, mono, body["raw_sha256"], len(raw), zlib.compress(raw, 1), previous, record_hash, self.epoch))
                if mono <= mono_previous or wall < wall_previous or abs((wall - wall_previous) - (mono - mono_previous)) > 10 ** 9:
                    self.db.execute("INSERT INTO issue VALUES(?,?,?,?)", (sequence, "CLOCK_DISCONTINUITY",
                        "receipt wall/monotonic clocks disagree", time.time_ns()))
                previous, wall_previous, mono_previous = record_hash, wall, mono
                sequences.append(sequence)
            self.db.execute("INSERT INTO flush_batch(first_sequence,last_sequence) VALUES(?,?)", (start, sequence))
        # Only update the in-memory chain after the FULL raw commit succeeds.
        self.sequence, self.previous, self.wall, self.mono = sequence, previous, wall_previous, mono_previous
        self.raw_committed = time.time_ns()
        return sequences

    def consume(self, items, idl, subscription, entries=None):
        sequences = self.append_batch(items)
        if not sequences:
            return subscription, False
        decoded, bad_subscription, received = [], False, False
        for sequence, (raw, wall, mono) in zip(sequences, items):
            try:
                message = json.loads(raw)
                if subscription is None:
                    if message.get("id") != 1 or type(message.get("result")) is not int:
                        raise Refused("subscription was not acknowledged")
                    subscription = message["result"]
                    decoded.append((sequence, [], {"subscription_ack": 1}, subscription, None, wall, None))
                else:
                    births, stats = BS.decode_notification(message, idl, subscription, entries)
                    slot = message["params"]["result"]["context"]["slot"]
                    decoded.append((sequence, births, stats, None, slot, wall, None))
                    received = True
            except Exception as error:
                bad_subscription |= subscription is None
                decoded.append((sequence, [], {}, None, None, wall, type(error).__name__ + ": " + str(error)))
        with self.db:
            for sequence, births, stats, acknowledgement, slot, wall, error in decoded:
                if error is not None:
                    self.db.execute("INSERT INTO issue VALUES(?,?,?,?)", (sequence, "DECODE_REFUSED", error, time.time_ns()))
                    self.db.execute("UPDATE raw_frame SET decode_status='REFUSED' WHERE sequence=?", (sequence,))
                    continue
                self.materialize(sequence, births, stats, commit=False)
                if acknowledgement is not None:
                    self.acknowledge(sequence, acknowledgement, commit=False)
                if slot is not None:
                    self.notification_received(sequence, slot, wall, commit=False)
            self.db.execute("UPDATE flush_batch SET raw_committed_unix_nanos=? WHERE first_sequence=?",
                            (self.raw_committed, sequences[0]))
        available = time.time_ns()  # actual post-derived-commit clock, never the earlier receipt
        with self.db:
            self.db.execute("UPDATE flush_batch SET derived_committed_unix_nanos=? WHERE first_sequence=?",
                            (available, sequences[0]))
        if bad_subscription:
            raise BS.TransportLost("subscription failure; raw batch retained")
        return subscription, received


def run(path, seconds, max_bytes):
    import websocket
    if not math.isfinite(seconds) or seconds <= 0 or max_bytes <= BS.MAX_FRAME_BYTES:
        raise Refused("bounded positive duration and capacity required")
    idl = BS.load_idl()
    entries = BS.B9D.event_entries(idl)
    recorder = Recorder(path, max_bytes=max_bytes, duration_seconds=seconds)
    recorder.received_count = 0
    deadline = time.monotonic() + seconds
    reason, failures, last_status = "DURATION_COMPLETE", 0, time.monotonic()
    transport_errors = (websocket.WebSocketException, OSError, TimeoutError)
    request = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
               "params": [{"mentions": [BS.B9D.PUMP_PROGRAM]}, {"commitment": BS.COMMITMENT}]}
    try:
        while time.monotonic() < deadline:
            if recorder.bytes_on_disk() >= max_bytes or BS.shutil.disk_usage(path.parent).free < BS.RESERVE_BYTES:
                reason = "CAPACITY_STOP"
                recorder.issue(None, reason, "bounded capture stopped; no files removed")
                break
            recorder.begin_connection()
            socket, subscription, outcome = None, None, "DURATION_COMPLETE"
            buffer, buffered_bytes, batch_start = [], 0, time.monotonic()
            last_data, next_capacity = time.monotonic(), time.monotonic()

            def flush():
                nonlocal buffer, buffered_bytes, batch_start, subscription, failures, reason
                items, buffer = buffer, []  # never retry an uncertain disk commit
                buffered_bytes = 0
                if items:
                    subscription, received = recorder.consume(items, idl, subscription, entries)
                    if received:
                        failures = 0
                    if recorder.bytes_on_disk() >= max_bytes:
                        reason = "CAPACITY_STOP"
                batch_start = time.monotonic()

            try:
                try:
                    socket = websocket.create_connection(BS.ENDPOINT, timeout=max(0.01, min(10, deadline - time.monotonic())), suppress_origin=True)
                    socket.send(json.dumps(request))
                except transport_errors as error:
                    raise BS.TransportLost(type(error).__name__ + ": " + str(error)) from error
                while time.monotonic() < deadline:
                    if reason == "CAPACITY_STOP":
                        outcome = reason
                        recorder.issue(None, reason, "bounded capture stopped; no files removed")
                        break
                    now = time.monotonic()
                    if now >= next_capacity:
                        if recorder.bytes_on_disk() >= max_bytes or BS.shutil.disk_usage(path.parent).free < BS.RESERVE_BYTES:
                            flush()
                            reason = outcome = "CAPACITY_STOP"
                            recorder.issue(None, reason, "bounded capture stopped; no files removed")
                            break
                        next_capacity = now + 0.25
                    if buffer and (now - batch_start >= BATCH_SECONDS or len(buffer) >= BATCH_FRAMES or buffered_bytes >= BATCH_BYTES):
                        flush()
                        continue
                    timeout = min(1, deadline - now, max(0.001, BATCH_SECONDS - (now - batch_start)) if buffer else 1)
                    try:
                        socket.settimeout(max(0.001, timeout))
                        data = socket.recv()
                        wall, mono = time.time_ns(), time.monotonic_ns()
                    except websocket.WebSocketTimeoutException as error:
                        flush()
                        if time.monotonic() - last_data >= BS.STALE_SECONDS:
                            raise BS.TransportLost("no data for 30 seconds; reconnecting stale transport") from error
                        continue
                    except transport_errors as error:
                        raise BS.TransportLost(type(error).__name__ + ": " + str(error)) from error
                    if not data:
                        raise BS.TransportLost("websocket closed without a data frame")
                    recorder.received_count += 1
                    if not buffer:
                        batch_start = time.monotonic()
                    last_data = time.monotonic()
                    raw = data.encode() if isinstance(data, str) else data
                    if len(raw) > BS.MAX_FRAME_BYTES:
                        raise Refused("frame size exceeds recorder bound")
                    buffer.append((raw, wall, mono))
                    buffered_bytes += len(raw)
                    if time.monotonic() - last_status >= 20:
                        flush()
                        print(json.dumps({"status": "RECORDING_NO_TRADE", "frames": recorder.sequence,
                                          "connection_epoch": recorder.epoch, "bytes": recorder.bytes_on_disk()}), flush=True)
                        last_status = time.monotonic()
                flush()
            except BS.TransportLost as error:
                flush()  # drain received raw frames BEFORE recording the outage boundary
                outcome = "TRANSPORT_GAP"
                failures += 1
                recorder.gap(str(error))
                print(json.dumps({"status": "RECONNECTING_NO_TRADE", "error": str(error)}), flush=True)
            except KeyboardInterrupt:
                flush()
                outcome = "INTERRUPTED"
                raise
            except BaseException:
                outcome = "CAPTURE_FAILURE"
                raise
            finally:
                if socket is not None:
                    try:
                        socket.close(timeout=1)
                    except Exception as error:
                        recorder.issue(None, "CLOSE_ERROR", str(error))
                    finally:
                        try:
                            socket.shutdown()
                        except Exception as error:
                            recorder.issue(None, "SHUTDOWN_ERROR", str(error))
                recorder.end_connection(outcome)
            if reason == "CAPACITY_STOP":
                break
            if outcome == "TRANSPORT_GAP":
                delay = min(30, 2 ** min(max(failures - 1, 0), 5), max(0, deadline - time.monotonic()))
                if delay:
                    time.sleep(delay)
    except KeyboardInterrupt:
        reason = "INTERRUPTED"
        recorder.issue(None, reason, "operator interrupted capture")
    except Exception as error:
        reason = "CAPTURE_FAILURE"
        recorder.issue(None, reason, type(error).__name__ + ": " + str(error))
    return recorder.finish(reason)


def status(path):
    result = BS.status(path)
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        last = db.execute("SELECT observation_json FROM create_observation ORDER BY frame_sequence DESC LIMIT 1").fetchone()
        if last:
            observation = json.loads(last[0])
            result["latest_creation_receipt_lag_seconds"] = observation["received_unix_nanos"] / 1e9 - observation["fields"]["timestamp"]
            result["latest_creation_slot"] = observation["slot"]
        result["chain_head_freshness"] = "REQUIRES_RPC_HEAD_CHECK; local receipt age alone is insufficient"
    finally:
        db.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--status", type=Path)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--max-mib", type=int, default=128)
    args = parser.parse_args()
    result = status(args.status) if args.status else run(args.out, args.seconds, args.max_mib * 1024 ** 2)
    print(json.dumps(result, sort_keys=True), flush=True)
    if not args.status and result["end_reason"] not in {"DURATION_COMPLETE", "INTERRUPTED"}:
        raise SystemExit(1)
