"""The same transport attack suite, plus batch durability and rollback controls."""
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import birth_stream as BS, birth_stream_fast as FAST
from scripts.birth_origin import Refused
from scripts.birth_stream_verify import verify
from scripts import test_birth_stream_reconnect as RC
from scripts.test_birth_stream_reconnect import ack, notification


class FastReconnectTests(RC.ReconnectTests):
    def run_capture(self, *args, **kwargs):
        with patch.object(BS, "run", FAST.run):
            return super().run_capture(*args, **kwargs)


class BatchTests(unittest.TestCase):
    def test_all_raw_durable_before_first_decode_and_receipts_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.sqlite"
            rec = FAST.Recorder(path, max_bytes=16 * 1024 ** 2)
            items = [(json.dumps(data).encode(), time.time_ns(), time.monotonic_ns()) for data in (ack(), notification(), notification())]
            original = BS.decode_notification
            def check(*args):
                reader = sqlite3.connect(path)
                rows = reader.execute("SELECT count(*) FROM raw_frame").fetchone()[0]
                reader.close()
                self.assertEqual(rows, 3)
                return original(*args)
            with patch.object(BS, "decode_notification", side_effect=check):
                rec.consume(items, BS.load_idl(), None)
            rec.finish("TEST")
            report, observations = verify(path)
            self.assertEqual(report["raw_replay"], "EXACT")
            self.assertEqual([o["received_unix_nanos"] for o in observations], [items[1][1], items[2][1]])

    def test_raw_batch_failure_rolls_back_disk_and_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            rec = FAST.Recorder(Path(directory) / "batch.sqlite", max_bytes=16 * 1024 ** 2)
            with patch.object(BS, "MAX_FRAME_BYTES", 10):
                with self.assertRaises(Refused):
                    rec.append_batch([(b"a", time.time_ns(), time.monotonic_ns()), (b"a" * 11, time.time_ns(), time.monotonic_ns())])
            self.assertEqual(rec.sequence, 0)
            self.assertEqual(rec.previous, "0" * 64)
            self.assertEqual(rec.db.execute("SELECT count(*) FROM raw_frame").fetchone()[0], 0)
            rec.finish("TEST")

    def test_derived_failure_keeps_raw_pending_and_never_retries_as_network(self):
        with tempfile.TemporaryDirectory() as directory:
            rec = FAST.Recorder(Path(directory) / "batch.sqlite", max_bytes=16 * 1024 ** 2)
            items = [(json.dumps(data).encode(), time.time_ns(), time.monotonic_ns()) for data in (ack(), notification())]
            original = rec.materialize
            def fail_second(sequence, *args, **kwargs):
                if sequence == 2:
                    raise sqlite3.OperationalError("fixture failure")
                return original(sequence, *args, **kwargs)
            with patch.object(rec, "materialize", side_effect=fail_second):
                with self.assertRaises(sqlite3.OperationalError):
                    rec.consume(items, BS.load_idl(), None)
            self.assertEqual(rec.db.execute("SELECT count(*) FROM raw_frame WHERE decode_status='PENDING'").fetchone()[0], 2)
            self.assertEqual(rec.db.execute("SELECT count(*) FROM create_observation").fetchone()[0], 0)
            rec.finish("TEST")


if __name__ == "__main__":
    unittest.main()
