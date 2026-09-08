"""Deterministic end-to-end transport attacks; no network and no real sleeps."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import websocket
from scripts import birth_stream as BS
from scripts.birth_origin import Refused
from scripts.birth_stream_verify import verify
from scripts.test_birth_stream import message


class Clock:
    def __init__(self):
        self.now, self.sleeps = 1000.0, []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Socket:
    def __init__(self, clock, actions, *, close_error=False):
        self.clock, self.actions = clock, list(actions)
        self.sent, self.closed, self.shutdowns = [], 0, 0
        self.close_error = close_error

    def send(self, value):
        self.sent.append(json.loads(value))

    def settimeout(self, value):
        self.timeout = value

    def recv(self):
        if not self.actions:
            self.clock.now += self.timeout
            raise websocket.WebSocketTimeoutException("fixture timeout")
        self.clock.now += 0.1
        value = self.actions.pop(0)
        if isinstance(value, BaseException):
            raise value
        return json.dumps(value) if isinstance(value, dict) else value

    def close(self, timeout):
        self.closed += 1
        if self.close_error:
            raise websocket.WebSocketProtocolException("invalid close 1006")

    def shutdown(self):
        self.shutdowns += 1


def ack(subscription=7):
    return {"jsonrpc": "2.0", "id": 1, "result": subscription}


def notification(subscription=7):
    data = message()
    data["params"]["subscription"] = subscription
    return data


class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "capture.sqlite"
        self.clock = Clock()

    def run_capture(self, sockets, *, seconds=4, capacity=False, materialize_error=False):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(BS.time, "monotonic", side_effect=lambda: self.clock.now))
            stack.enter_context(patch.object(BS.time, "monotonic_ns", side_effect=lambda: int(self.clock.now * 1e9)))
            stack.enter_context(patch.object(BS.time, "time_ns", side_effect=lambda: 1788890000000000000 + int(self.clock.now * 1e9)))
            stack.enter_context(patch.object(BS.time, "sleep", side_effect=self.clock.sleep))
            stack.enter_context(patch.object(BS.shutil, "disk_usage", return_value=SimpleNamespace(free=0 if capacity else 100 * 1024 ** 3)))
            factory = stack.enter_context(patch.object(websocket, "create_connection", side_effect=sockets))
            if materialize_error:
                stack.enter_context(patch.object(BS.Recorder, "materialize", side_effect=sqlite3.OperationalError("fixture disk fault")))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            result = BS.run(self.path, seconds, 8 * 1024 ** 2)
        return result, factory.call_count

    def test_1006_recovers_resubscribes_and_replays_across_new_subscription(self):
        first = Socket(self.clock, [ack(), notification(), websocket.WebSocketProtocolException("Invalid close opcode 1006")])
        second = Socket(self.clock, [ack(99), notification(99)])
        result, calls = self.run_capture([first, second])
        self.assertEqual(calls, 2)
        self.assertEqual(result["end_reason"], "DURATION_COMPLETE")
        self.assertEqual(result["unrepaired_gaps"], 1)
        self.assertEqual(result["create_observations"], 2)
        self.assertEqual(first.sent, second.sent)
        self.assertEqual(first.shutdowns, 1)
        replay, observations = verify(self.path)
        self.assertEqual(replay["raw_replay"], "EXACT")
        self.assertEqual([o["connection_epoch"] for o in observations], [1, 2])
        self.assertGreater(observations[1]["received_unix_nanos"], observations[0]["received_unix_nanos"])
        self.assertEqual(replay["duplicate_create_observations"], 1)  # retained; not new independent births
        gap = replay["unrepaired_gaps"][0]
        self.assertEqual(gap["resumed_sequence"], 4)  # acknowledgement at 3 is NOT resumption
        self.assertEqual(gap["coverage"], "UNKNOWN_UNREPAIRED")

    def test_same_subscription_number_still_has_new_epoch(self):
        first = Socket(self.clock, [ack(), notification(), ""])
        second = Socket(self.clock, [ack(), notification()])
        result, _ = self.run_capture([first, second])
        self.assertEqual(result["connection_epochs"], 2)
        self.assertEqual(verify(self.path)[0]["raw_replay"], "EXACT")

    def test_repeated_connect_failures_have_backoff_and_do_not_extend_deadline(self):
        result, calls = self.run_capture([OSError("down")] * 20, seconds=70)
        self.assertEqual(self.clock.sleeps, [1, 2, 4, 8, 16, 30, 9])
        self.assertEqual(calls, 7)
        self.assertEqual(result["frames"], 0)
        self.assertEqual(result["unrepaired_gaps"], 1)
        self.assertEqual(self.clock.now, 1070)
        self.assertEqual(verify(self.path)[0]["raw_replay"], "EXACT")

    def test_clean_close_and_close_method_failure_do_not_kill_recovery(self):
        first = Socket(self.clock, [ack(), ""], close_error=True)
        second = Socket(self.clock, [ack(), notification()])
        result, calls = self.run_capture([first, second])
        self.assertEqual(calls, 2)
        self.assertEqual(first.shutdowns, 1)
        self.assertEqual(result["end_reason"], "DURATION_COMPLETE")
        self.assertEqual(verify(self.path)[0]["creates"], 1)

    def test_silent_socket_is_replaced_after_staleness(self):
        first = Socket(self.clock, [ack()])
        second = Socket(self.clock, [ack(), notification()])
        result, calls = self.run_capture([first, second], seconds=38)
        self.assertEqual(calls, 2)
        self.assertEqual(result["create_observations"], 1)
        self.assertIn("30 seconds", verify(self.path)[0]["unrepaired_gaps"][0]["detail"])

    def test_subscription_error_is_raw_evidence_and_reconnects(self):
        first = Socket(self.clock, [{"id": 1, "error": {"code": -1}}])
        second = Socket(self.clock, [ack(), notification()])
        result, calls = self.run_capture([first, second])
        self.assertEqual(calls, 2)
        replay, _ = verify(self.path)
        self.assertEqual(replay["refused_frames"], 1)
        self.assertEqual(result["create_observations"], 1)

    def test_storage_failure_is_fatal_not_misreported_as_transport(self):
        result, calls = self.run_capture([Socket(self.clock, [ack()])], materialize_error=True)
        self.assertEqual(calls, 1)
        self.assertEqual(result["end_reason"], "CAPTURE_FAILURE")
        self.assertEqual(result["pending_raw_frames"], 1)
        self.assertEqual(result["unrepaired_gaps"], 0)

    def test_capacity_stop_does_not_retry(self):
        result, calls = self.run_capture([], capacity=True)
        self.assertEqual(calls, 0)
        self.assertEqual(result["end_reason"], "CAPACITY_STOP")

    def test_interrupt_preserves_closed_session_and_does_not_retry(self):
        first = Socket(self.clock, [ack(), notification(), KeyboardInterrupt()])
        result, calls = self.run_capture([first])
        self.assertEqual(calls, 1)
        self.assertEqual(result["end_reason"], "INTERRUPTED")
        self.assertEqual(verify(self.path)[0]["raw_replay"], "EXACT")

    def test_deleted_gap_cannot_claim_continuity(self):
        first = Socket(self.clock, [ack(), notification(), ""])
        second = Socket(self.clock, [ack(), notification()])
        self.run_capture([first, second])
        db = sqlite3.connect(self.path)
        db.execute("DELETE FROM capture_gap")
        db.commit()
        db.close()
        with self.assertRaises(Refused):
            verify(self.path)

    def test_ack_only_is_not_healthy_and_stale_data_is_not_healthy(self):
        rec = BS.Recorder(self.path, max_bytes=8 * 1024 ** 2)
        try:
            seq = rec.append(json.dumps(ack()).encode(), BS.time.time_ns(), BS.time.monotonic_ns())
            rec.materialize(seq, [], {"subscription_ack": 1})
            rec.acknowledge(seq, 7)
            self.assertEqual(BS.status(self.path)["health"], "STALE_OR_CONNECTING")
            wall = BS.time.time_ns()
            seq = rec.append(json.dumps(notification()).encode(), wall, BS.time.monotonic_ns())
            births, stats = BS.decode_notification(notification(), BS.load_idl(), 7)
            rec.materialize(seq, births, stats)
            rec.notification_received(seq, 123, wall)
            self.assertEqual(BS.status(self.path)["health"], "RECEIVING_UNVERIFIED_NO_TRADE")
            with patch.object(BS.time, "time_ns", return_value=wall + 31 * 10 ** 9):
                self.assertEqual(BS.status(self.path)["health"], "STALE_OR_CONNECTING")
        finally:
            rec.finish("TEST")


if __name__ == "__main__":
    unittest.main()
