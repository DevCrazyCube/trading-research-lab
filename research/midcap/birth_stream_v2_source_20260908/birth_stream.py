"""Bounded, read-only recorder of the Pump creation event stream.

Every websocket frame is durably stored before decoding. All creation regimes are
retained, including failed-transaction evidence. No ranked endpoint, price filter,
credentials, signing, order submission, or trading decision exists here.

python -m scripts.birth_stream --out <new.sqlite> --seconds 60 --max-mib 128
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import time
import zlib

from scripts import b9d_transaction_bodies as B9D
from scripts.birth_origin import ROOT, Refused, canonical

ENDPOINT = "wss://api.mainnet.solana.com"
COMMITMENT = "finalized"
SOURCE = "SOLANA_PUBLIC_FINALIZED_LOGS"
MAX_FRAME_BYTES = 4 * 1024 * 1024
RESERVE_BYTES = 16 * 1024 ** 3
STALE_SECONDS = 30


class TransportLost(Exception):
    """Recoverable socket/subscription failure, never a storage or decoder bug."""


def load_idl():
    raw = (ROOT / B9D.PUMP_IDL_PATH).read_bytes()
    if hashlib.sha256(raw).hexdigest() != B9D.PUMP_IDL_SHA256:
        raise Refused("pinned creation IDL changed")
    return json.loads(raw)


def decode_notification(message, idl, subscription):
    """Strict invoking-program binding. A log index is NOT an instruction index."""
    if message.get("method") != "logsNotification":
        raise Refused("unexpected notification method")
    params = message.get("params") or {}
    if params.get("subscription") != subscription:
        raise Refused("wrong subscription identity")
    result = params.get("result") or {}
    slot = (result.get("context") or {}).get("slot")
    value = result.get("value") or {}
    signature, logs = value.get("signature"), value.get("logs")
    if type(slot) is not int or slot < 0 or not isinstance(signature, str) or not signature:
        raise Refused("missing notification slot or signature")
    if not isinstance(logs, list) or any(not isinstance(line, str) for line in logs):
        raise Refused("missing or malformed transaction logs")
    if "err" not in value:
        raise Refused("transaction success is unknown")
    entries = B9D.event_entries(idl)
    births, stack = [], []
    stats = Counter()
    for index, line in enumerate(logs):
        if "log truncated" in line.lower() or "logs truncated" in line.lower():
            raise Refused("truncated transaction logs")
        invoked = re.fullmatch(r"Program (\S+) invoke \[(\d+)\]", line)
        ended = re.fullmatch(r"Program (\S+) (success|failed:.*)", line)
        if invoked:
            if int(invoked.group(2)) != len(stack) + 1:
                raise Refused("invocation stack depth mismatch")
            stack.append(invoked.group(1))
            continue
        if ended:
            if not stack or stack[-1] != ended.group(1):
                raise Refused("invocation stack program mismatch")
            stack.pop()
            continue
        if not line.startswith("Program data:"):
            continue
        if not stack:
            raise Refused("unparented program data")
        if stack[-1] != B9D.PUMP_PROGRAM:
            stats["other_program_data"] += 1
            continue
        try:
            payload = base64.b64decode(line[len("Program data:"):].strip(), validate=True)
        except ValueError as error:
            raise Refused("invalid event base64") from error
        entry = entries.get(payload[:8])
        if entry is None:
            raise Refused("unknown Pump event discriminator " + payload[:8].hex())
        stats[entry[0]] += 1
        if entry[0] != "CreateEvent":
            continue  # fully retained raw, known non-creation event; not decoded as a trade
        _, fields = B9D.decode_idl_event(idl, payload)
        births.append({"slot": slot, "signature": signature, "log_index": index,
                       "transaction_index": None, "outer_instruction_index": None,
                       "inner_instruction_index": None, "canonical_status": "UNRECONCILED_LOG_OBSERVATION",
                       "event_payload_base64": base64.b64encode(payload).decode(),
                       "event_payload_sha256": hashlib.sha256(payload).hexdigest(),
                       "transaction_succeeded": value["err"] is None, "fields": fields})
    if stack:
        raise Refused("incomplete invocation stack")
    return births, dict(stats)


class Recorder:
    def __init__(self, path, *, max_bytes, duration_seconds=None):
        if path.exists():
            raise Refused("recorder requires a new file; prior sessions are never overwritten")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive claim before sqlite opens it; another writer cannot share this session.
        with path.open("xb"):
            pass
        self.path, self.max_bytes = path, max_bytes
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE session (id INTEGER PRIMARY KEY CHECK(id=1), manifest_json TEXT NOT NULL,
                                end_json TEXT);
          CREATE TABLE raw_frame (sequence INTEGER PRIMARY KEY, received_unix_nanos INTEGER NOT NULL,
              received_monotonic_nanos INTEGER NOT NULL, raw_sha256 TEXT NOT NULL,
              raw_bytes INTEGER NOT NULL, raw_zlib BLOB NOT NULL,
              previous_sha256 TEXT NOT NULL, record_sha256 TEXT NOT NULL,
              decode_status TEXT NOT NULL DEFAULT 'PENDING', accounting_json TEXT,
              connection_epoch INTEGER NOT NULL);
          CREATE TABLE create_observation (frame_sequence INTEGER NOT NULL, log_index INTEGER NOT NULL,
              signature TEXT NOT NULL, slot INTEGER NOT NULL, succeeded INTEGER NOT NULL,
              payload_sha256 TEXT NOT NULL, observation_json TEXT NOT NULL,
              PRIMARY KEY(frame_sequence,log_index), FOREIGN KEY(frame_sequence) REFERENCES raw_frame(sequence));
          CREATE TABLE issue (sequence INTEGER, kind TEXT NOT NULL, detail TEXT NOT NULL,
                              recorded_unix_nanos INTEGER NOT NULL);
          CREATE TABLE connection_epoch (id INTEGER PRIMARY KEY, first_sequence INTEGER NOT NULL,
              started_unix_nanos INTEGER NOT NULL, end_sequence INTEGER, ended_unix_nanos INTEGER,
              outcome TEXT, subscription_id INTEGER, ack_sequence INTEGER,
              last_notification_sequence INTEGER, last_notification_slot INTEGER);
          CREATE TABLE capture_gap (id INTEGER PRIMARY KEY, after_sequence INTEGER NOT NULL,
              started_unix_nanos INTEGER NOT NULL, detected_unix_nanos INTEGER NOT NULL,
              before_epoch INTEGER NOT NULL, last_observed_slot INTEGER, detail TEXT NOT NULL,
              resumed_sequence INTEGER, resumed_unix_nanos INTEGER, resumed_epoch INTEGER,
              resumed_slot INTEGER, coverage TEXT NOT NULL DEFAULT 'UNKNOWN_UNREPAIRED');
        """)
        self.sequence, self.previous, self.epoch = 0, "0" * 64, 0
        self.wall, self.mono = time.time_ns(), time.monotonic_ns()
        manifest = {"schema": "birth-stream-v2", "source": SOURCE, "endpoint": ENDPOINT,
                    "commitment": COMMITMENT, "started_unix_nanos": self.wall,
                    "started_monotonic_nanos": self.mono, "max_bytes": max_bytes,
                    "duration_seconds": duration_seconds,
                    "planned_stop_unix_nanos": self.wall + int(duration_seconds * 1e9) if duration_seconds else None,
                    "idl_sha256": B9D.PUMP_IDL_SHA256,
                    "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "borsh_decoder_sha256": hashlib.sha256((ROOT / "scripts/b9d_transaction_bodies.py").read_bytes()).hexdigest(),
                    "status": "OBSERVATION_ONLY_NO_TRADE", "capture": "all raw websocket data frames before decode",
                    "coverage": "UNMEASURED_SINGLE_SOURCE", "canonical_order": "requires independent reconciliation",
                    "fsync": "SQLite synchronous FULL; raw commit precedes decode commit",
                    "reconnect": "1,2,4,8,16,30 second capped backoff; one fixed session deadline",
                    "silence_reconnect_seconds": STALE_SECONDS,
                    "gap_policy": "explicit UNKNOWN_UNREPAIRED; no backfill or continuous-history assertion"}
        self.db.execute("INSERT INTO session VALUES (1,?,NULL)", (canonical(manifest).decode(),))
        self.db.commit()

    def issue(self, sequence, kind, detail):
        self.db.execute("INSERT INTO issue VALUES (?,?,?,?)", (sequence, kind, detail, time.time_ns()))
        self.db.commit()

    def begin_connection(self):
        self.epoch += 1
        self.db.execute("INSERT INTO connection_epoch(id,first_sequence,started_unix_nanos) VALUES(?,?,?)",
                        (self.epoch, self.sequence + 1, time.time_ns()))
        self.db.commit()

    def end_connection(self, outcome):
        if self.epoch:
            self.db.execute("UPDATE connection_epoch SET end_sequence=?,ended_unix_nanos=?,outcome=? "
                            "WHERE id=? AND end_sequence IS NULL", (self.sequence, time.time_ns(), outcome, self.epoch))
            self.db.commit()

    def gap(self, detail):
        self.issue(None, "TRANSPORT_GAP", detail)
        if not self.db.execute("SELECT 1 FROM capture_gap WHERE resumed_sequence IS NULL").fetchone():
            last = self.db.execute("SELECT last_notification_slot FROM connection_epoch "
                                   "WHERE last_notification_slot IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
            self.db.execute("INSERT INTO capture_gap(after_sequence,started_unix_nanos,detected_unix_nanos,"
                            "before_epoch,last_observed_slot,detail) VALUES(?,?,?,?,?,?)",
                            (self.sequence, self.wall, time.time_ns(), self.epoch, last[0] if last else None, detail))
            self.db.commit()

    def append(self, raw, wall, mono):
        if len(raw) > MAX_FRAME_BYTES:
            raise Refused("frame size exceeds recorder bound")
        if not self.epoch:
            self.begin_connection()
        self.sequence += 1
        body = {"sequence": self.sequence, "received_unix_nanos": wall,
                "received_monotonic_nanos": mono, "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_bytes": len(raw), "previous_sha256": self.previous, "connection_epoch": self.epoch}
        record_hash = hashlib.sha256(canonical(body)).hexdigest()
        self.db.execute("INSERT INTO raw_frame(sequence,received_unix_nanos,received_monotonic_nanos,"
                        "raw_sha256,raw_bytes,raw_zlib,previous_sha256,record_sha256,connection_epoch) VALUES (?,?,?,?,?,?,?,?,?)",
                        (self.sequence, wall, mono, body["raw_sha256"], len(raw), zlib.compress(raw), self.previous, record_hash, self.epoch))
        self.db.commit()  # raw is recoverable even if the decoder crashes next
        if mono <= self.mono or wall < self.wall or abs((wall - self.wall) - (mono - self.mono)) > 1_000_000_000:
            self.issue(self.sequence, "CLOCK_DISCONTINUITY", "receipt wall/monotonic clocks disagree")
        self.wall, self.mono, self.previous = wall, mono, record_hash
        return self.sequence

    def materialize(self, sequence, births, stats):
        frame = self.db.execute("SELECT received_unix_nanos,received_monotonic_nanos,connection_epoch FROM raw_frame WHERE sequence=?", (sequence,)).fetchone()
        if frame is None:
            raise Refused("cannot materialize without persisted raw frame")
        with self.db:  # a partial transaction's creates must never survive a decode failure
            for birth in births:
                event_time = birth["fields"]["timestamp"] * 1_000_000_000
                evidence = {**birth, "source": SOURCE, "commitment_at_observation": COMMITMENT,
                            "provenance": "observed_live", "received_unix_nanos": frame[0],
                            "received_monotonic_nanos": frame[1], "frame_sequence": sequence,
                            "connection_epoch": frame[2],
                            "event_time_unix_nanos": event_time,
                            "publication_not_after_receipt": event_time <= frame[0],
                            "status": "NO_TRADE"}
                self.db.execute("INSERT INTO create_observation VALUES(?,?,?,?,?,?,?)",
                    (sequence, birth["log_index"], birth["signature"], birth["slot"],
                     int(birth["transaction_succeeded"]), birth["event_payload_sha256"], canonical(evidence).decode()))
            self.db.execute("UPDATE raw_frame SET decode_status='CLASSIFIED',accounting_json=? WHERE sequence=?",
                            (canonical(stats).decode(), sequence))

    def acknowledge(self, sequence, subscription):
        self.db.execute("UPDATE connection_epoch SET subscription_id=?,ack_sequence=? WHERE id=?",
                        (subscription, sequence, self.epoch))
        self.db.commit()

    def notification_received(self, sequence, slot, wall):
        with self.db:
            self.db.execute("UPDATE connection_epoch SET last_notification_sequence=?,last_notification_slot=? WHERE id=?",
                            (sequence, slot, self.epoch))
            # Resumption records observed time only; the outage remains unrepaired forever.
            self.db.execute("UPDATE capture_gap SET resumed_sequence=?,resumed_unix_nanos=?,resumed_epoch=?,resumed_slot=? "
                            "WHERE resumed_sequence IS NULL", (sequence, wall, self.epoch, slot))

    def bytes_on_disk(self):
        return sum(p.stat().st_size for p in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")) if p.exists())

    def finish(self, reason):
        self.end_connection(reason)
        births = self.db.execute("SELECT count(*),count(DISTINCT signature),sum(succeeded) FROM create_observation").fetchone()
        summary = {"status": "OBSERVATION_ONLY_NO_TRADE", "end_reason": reason,
                   "finished_unix_nanos": time.time_ns(), "frames": self.sequence,
                   "create_observations": births[0], "create_transactions": births[1],
                   "successful_create_observations": births[2] or 0,
                   "issues": self.db.execute("SELECT count(*) FROM issue").fetchone()[0],
                   "pending_raw_frames": self.db.execute("SELECT count(*) FROM raw_frame WHERE decode_status='PENDING'").fetchone()[0],
                   "frame_chain_tail": self.previous, "bytes_before_checkpoint": self.bytes_on_disk(),
                   "coverage": "UNMEASURED_SINGLE_SOURCE", "canonical_reconciliation": "PENDING",
                   "connection_epochs": self.epoch, "reconnect_attempts": max(0, self.epoch - 1),
                   "unrepaired_gaps": self.db.execute("SELECT count(*) FROM capture_gap").fetchone()[0]}
        self.db.execute("UPDATE session SET end_json=? WHERE id=1", (canonical(summary).decode(),))
        self.db.commit()
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.close()
        return summary


def run(path, seconds, max_bytes):
    import websocket
    if not math.isfinite(seconds) or seconds <= 0 or max_bytes <= MAX_FRAME_BYTES:
        raise Refused("positive duration and at least one maximum frame of capacity required")
    idl = load_idl()
    recorder = Recorder(path, max_bytes=max_bytes, duration_seconds=seconds)
    deadline = time.monotonic() + seconds
    reason, failures, last_status = "DURATION_COMPLETE", 0, time.monotonic()
    request = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
               "params": [{"mentions": [B9D.PUMP_PROGRAM]}, {"commitment": COMMITMENT}]}
    transport_errors = (websocket.WebSocketException, OSError, TimeoutError)
    try:
        while time.monotonic() < deadline:
            if recorder.bytes_on_disk() >= max_bytes or shutil.disk_usage(path.parent).free < RESERVE_BYTES:
                reason = "CAPACITY_STOP"
                recorder.issue(None, reason, "bounded capture stopped; no files removed")
                break
            recorder.begin_connection()
            socket, subscription, outcome = None, None, "DURATION_COMPLETE"
            last_data = time.monotonic()
            try:
                try:
                    socket = websocket.create_connection(ENDPOINT, timeout=max(0.05, min(10, deadline - time.monotonic())), suppress_origin=True)
                    socket.send(json.dumps(request))
                except transport_errors as error:
                    raise TransportLost(type(error).__name__ + ": " + str(error)) from error
                while time.monotonic() < deadline:
                    if recorder.bytes_on_disk() >= max_bytes or shutil.disk_usage(path.parent).free < RESERVE_BYTES:
                        reason = outcome = "CAPACITY_STOP"
                        recorder.issue(None, reason, "bounded capture stopped; no files removed")
                        break
                    try:
                        socket.settimeout(max(0.05, min(5, deadline - time.monotonic())))
                        data = socket.recv()
                        wall, mono = time.time_ns(), time.monotonic_ns()
                    except websocket.WebSocketTimeoutException as error:
                        if time.monotonic() - last_data >= STALE_SECONDS:
                            raise TransportLost("no data for 30 seconds; reconnecting stale transport") from error
                        continue
                    except transport_errors as error:
                        raise TransportLost(type(error).__name__ + ": " + str(error)) from error
                    if not data:
                        raise TransportLost("websocket closed without a data frame")
                    last_data = time.monotonic()
                    raw = data.encode() if isinstance(data, str) else data
                    seq = recorder.append(raw, wall, mono)  # storage errors are fatal, never retried as network
                    try:
                        message = json.loads(raw)
                        if subscription is None:
                            if message.get("id") != 1 or type(message.get("result")) is not int:
                                raise Refused("subscription was not acknowledged")
                            new_subscription, births, stats = message["result"], [], {"subscription_ack": 1}
                        else:
                            births, stats = decode_notification(message, idl, subscription)
                    except Exception as error:
                        recorder.issue(seq, "DECODE_REFUSED", type(error).__name__ + ": " + str(error))
                        recorder.db.execute("UPDATE raw_frame SET decode_status='REFUSED' WHERE sequence=?", (seq,))
                        recorder.db.commit()
                        if subscription is None:
                            raise TransportLost("subscription failure") from error
                        continue
                    recorder.materialize(seq, births, stats)
                    if subscription is None:
                        subscription = new_subscription
                        recorder.acknowledge(seq, subscription)
                    else:
                        recorder.notification_received(seq, message["params"]["result"]["context"]["slot"], wall)
                        failures = 0  # a handshake alone does not reset outage backoff
                    if time.monotonic() - last_status >= 20:
                        print(json.dumps({"frames": recorder.sequence, "bytes": recorder.bytes_on_disk(),
                            "connection_epoch": recorder.epoch, "status": "RECORDING_NO_TRADE"}), flush=True)
                        last_status = time.monotonic()
            except TransportLost as error:
                outcome = "TRANSPORT_GAP"
                failures += 1
                recorder.gap(str(error))
                print(json.dumps({"status": "RECONNECTING_NO_TRADE", "connection_epoch": recorder.epoch,
                                  "error": str(error)}), flush=True)
            except BaseException:
                outcome = "INTERRUPTED_OR_CAPTURE_FAILURE"
                raise
            finally:
                if socket is not None:
                    try:
                        socket.close(timeout=1)
                    except Exception as error:
                        recorder.issue(None, "CLOSE_ERROR", type(error).__name__ + ": " + str(error))
                    finally:
                        try:
                            socket.shutdown()
                        except Exception as error:
                            recorder.issue(None, "SHUTDOWN_ERROR", type(error).__name__ + ": " + str(error))
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
    """Freshness is observed data, not a living PID. Also reads preserved v1 files."""
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        manifest, end = db.execute("SELECT manifest_json,end_json FROM session").fetchone()
        manifest, end = json.loads(manifest), json.loads(end) if end else None
        frames, last = db.execute("SELECT count(*),max(received_unix_nanos) FROM raw_frame").fetchone()
        epochs, gaps, last_notification = None, None, None
        if manifest["schema"] == "birth-stream-v2":
            epochs = db.execute("SELECT count(*) FROM connection_epoch").fetchone()[0]
            gaps = db.execute("SELECT count(*) FROM capture_gap").fetchone()[0]
            row = db.execute("SELECT received_unix_nanos FROM raw_frame WHERE sequence="
                             "(SELECT max(last_notification_sequence) FROM connection_epoch)").fetchone()
            last_notification = row[0] if row else None
        else:
            last_notification = last
        age = (time.time_ns() - last_notification) / 1e9 if last_notification else None
        health = ("STOPPED_" + end["end_reason"] if end else
                  "STALE_OR_CONNECTING" if age is None or age < 0 or age > STALE_SECONDS else
                  "RECEIVING_WITH_GAPS_NO_TRADE" if gaps else "RECEIVING_UNVERIFIED_NO_TRADE")
        return {"health": health, "frames": frames,
                "creates": db.execute("SELECT count(*) FROM create_observation").fetchone()[0],
                "last_frame_unix_nanos": last, "notification_age_seconds": age,
                "connection_epochs": epochs, "unrepaired_gaps": gaps,
                "issues": db.execute("SELECT count(*) FROM issue").fetchone()[0],
                "end": end, "coverage": "UNMEASURED_SINGLE_SOURCE", "status": "NO_TRADE"}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--status", type=Path, help="read-only live/closed capture health")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--max-mib", type=int, default=128)
    args = parser.parse_args()
    if args.status:
        print(json.dumps(status(args.status), sort_keys=True))
        return
    result = run(args.out, args.seconds, args.max_mib * 1024 ** 2)
    print(json.dumps(result, sort_keys=True))
    if result["end_reason"] not in {"DURATION_COMPLETE", "INTERRUPTED"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
