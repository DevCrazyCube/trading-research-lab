"""Negative controls for raw replay and log-to-canonical reconciliation."""
import base64
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import b9d_transaction_bodies as B9D
from scripts.birth_origin import Refused
from scripts.birth_stream import Recorder, decode_notification, load_idl
from scripts.birth_stream_verify import RPC, ReplayRPC, reconcile_one, sha, verify
from scripts.test_birth_stream import message, payload


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.sqlite"
        rec = Recorder(self.path, max_bytes=8 * 1024 ** 2)
        ack = json.dumps({"jsonrpc": "2.0", "id": 1, "result": 7}).encode()
        seq = rec.append(ack, time.time_ns(), time.monotonic_ns())
        rec.materialize(seq, [], {"subscription_ack": 1})
        rec.acknowledge(seq, 7)
        seq = rec.append(json.dumps(message()).encode(), time.time_ns(), time.monotonic_ns())
        births, stats = decode_notification(message(), load_idl(), 7)
        rec.materialize(seq, births, stats)
        rec.finish("TEST")

    def mutate(self, sql):
        db = sqlite3.connect(self.path)
        try:
            db.execute(sql)
            db.commit()
        finally:
            db.close()

    def test_exact_raw_replay(self):
        report, observations = verify(self.path)
        self.assertEqual(report["raw_replay"], "EXACT")
        self.assertEqual(report["frames"], 2)
        self.assertEqual(len(observations), 1)
        self.assertEqual(report["coverage"], "UNMEASURED_SINGLE_SOURCE")

    def test_corrupt_receipt_hash_refuses(self):
        self.mutate("UPDATE raw_frame SET received_unix_nanos=0 WHERE sequence=2")
        with self.assertRaises(Refused):
            verify(self.path)

    def test_changed_derived_identity_refuses(self):
        self.mutate("UPDATE create_observation SET signature='forged'")
        with self.assertRaises(Refused):
            verify(self.path)

    def test_deleted_frame_refuses(self):
        self.mutate("DELETE FROM raw_frame WHERE sequence=1")
        with self.assertRaises(Refused):
            verify(self.path)

    def test_pending_or_unclosed_capture_refuses(self):
        self.mutate("UPDATE session SET end_json=NULL")
        with self.assertRaises(Refused):
            verify(self.path)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        births, _ = decode_notification(message(), load_idl(), 7)
        self.observation = {**births[0], "signature": B9D.base58(bytes([9]) * 64),
                            "frame_sequence": 2, "received_unix_nanos": 1234567890}
        self.tx = {"slot": 123, "blockTime": 1000, "meta": {"err": None},
                   "transaction": [base64.b64encode(b"\x01" + bytes([9]) * 64).decode(), "base64"]}
        self.block = {"signatures": ["earlier", self.observation["signature"]], "blockTime": 1000}
        event = {"program_id": B9D.PUMP_PROGRAM, "data": B9D.ANCHOR_EVENT_CPI_TAG + payload(),
                 "outer_index": 3, "inner_index": 12}
        self.matches = [({"program_id": B9D.PUMP_PROGRAM}, event,
                         {"name": "CreateEvent", "fields": self.observation["fields"]})]

    def call(self):
        # Only envelope extraction is stubbed: identity/clock/hash/index checks run here;
        # actual wire/CPI parsing is additionally exercised on the preserved live pilot.
        with patch.object(B9D, "envelope_instructions", return_value=[]), patch.object(
                B9D, "associate_cpi_events", return_value=self.matches):
            return reconcile_one(self.observation, self.tx, self.block, {})

    def test_canonical_index_is_not_log_index(self):
        result = self.call()
        self.assertEqual(result["canonical_create_event"]["transaction_index"], 1)
        self.assertEqual(result["canonical_create_event"]["inner_instruction_index"], 12)
        self.assertNotEqual(result["log_index"], 12)
        self.assertEqual(result["first_received_unix_nanos"], 1234567890)

    def test_failed_transaction_never_becomes_birth(self):
        self.tx["meta"]["err"] = "failure"
        self.observation["transaction_succeeded"] = False
        self.assertEqual(self.call()["status"], "FAILED_TRANSACTION_NOT_A_BIRTH")

    def test_wrong_slot_signature_success_clock_or_missing_block_refuses(self):
        original = copy.deepcopy(self.tx)
        for change in ({"slot": 124}, {"blockTime": 999}, {"meta": {}}, {"meta": {"err": "failed"}},
                       {"transaction": [base64.b64encode(b"\x01" + bytes(64)).decode(), "base64"]}):
            self.tx = {**original, **change}
            with self.assertRaises(Refused):
                self.call()
        self.tx = original
        self.block["signatures"] = ["absent"]
        with self.assertRaises(B9D.FreezeViolation):
            self.call()

    def test_duplicate_or_absent_payload_match_refuses(self):
        self.matches *= 2
        with self.assertRaises(Refused):
            self.call()
        self.matches = []
        with self.assertRaises(Refused):
            self.call()


class RPCReplayTests(unittest.TestCase):
    def test_saved_bytes_replay_without_network_and_corruption_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            raw = json.dumps({"id": 1, "result": {"slot": 123}}).encode()
            (out / "rpc_0001.response").write_bytes(raw)
            receipt = {"endpoint": RPC, "http_status": 200, "response_bytes": len(raw),
                       "response_sha256": sha(raw), "request": {"id": 1, "method": "getTransaction", "params": ["sig"]}}
            (out / "rpc_0001.json").write_text(json.dumps(receipt))
            with patch("urllib.request.urlopen", side_effect=AssertionError("no network allowed")):
                replay = ReplayRPC(out)
                self.assertEqual(replay.call("getTransaction", ["sig"]), {"slot": 123})
                with self.assertRaises(Refused):
                    replay.call("getBlock", [123])
            (out / "rpc_0001.response").write_bytes(raw + b" ")
            with self.assertRaises(Refused):
                ReplayRPC(out)


if __name__ == "__main__":
    unittest.main()
