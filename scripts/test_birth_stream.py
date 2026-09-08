"""Receipt, program identity, raw persistence and exact creation decoding controls."""
import base64
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import time
import unittest
import zlib

from scripts import b9d_transaction_bodies as B9D
from scripts.birth_origin import Refused
from scripts.birth_stream import Recorder, decode_notification, load_idl


def payload(*, mayhem=0, quote=bytes(32)):
    def string(value):
        raw = value.encode()
        return struct.pack("<I", len(raw)) + raw
    # Synthetic addresses intentionally give user and creator different values.
    disc = next(bytes(e["discriminator"]) for e in load_idl()["events"] if e["name"] == "CreateEvent")
    return (disc + string("violet") + string("VIO") + string("ipfs://fixture")
            + bytes([1]) * 32 + bytes([2]) * 32 + bytes([3]) * 32 + bytes([4]) * 32
            + struct.pack("<qQQQQ", 1000, 1073000000000000, 30000000000, 793100000000000, 1000000000000000)
            + bytes([5]) * 32 + bytes([mayhem, 0]) + quote + struct.pack("<Q", 30000000000))


def message(raw=None, *, program=B9D.PUMP_PROGRAM, err=None):
    raw = payload() if raw is None else raw
    return {"method": "logsNotification", "params": {"subscription": 7,
        "result": {"context": {"slot": 123}, "value": {"signature": "fixture-signature", "err": err,
            "logs": [f"Program {program} invoke [1]", "Program data: " + base64.b64encode(raw).decode(),
                     f"Program {program} success"]}}}}


class BirthStreamTests(unittest.TestCase):
    def decode(self, data):
        return decode_notification(data, load_idl(), 7)

    def test_creator_and_uri_preserved(self):
        births, stats = self.decode(message())
        self.assertEqual(stats["CreateEvent"], 1)
        fields = births[0]["fields"]
        self.assertNotEqual(fields["creator"], fields["user"])
        self.assertEqual(fields["uri"], "ipfs://fixture")
        self.assertIsNone(births[0]["transaction_index"])
        self.assertIsNone(births[0]["outer_instruction_index"])

    def test_all_regimes_collected_without_price_or_graduation_filter(self):
        births, _ = self.decode(message(payload(mayhem=1, quote=bytes([6]) * 32)))
        self.assertTrue(births[0]["fields"]["is_mayhem_mode"])

    def test_failed_creation_is_evidence_not_successful_birth(self):
        births, _ = self.decode(message(err={"InstructionError": [0, "failure"]}))
        self.assertFalse(births[0]["transaction_succeeded"])

    def test_foreign_program_cannot_spoof_pump_creation(self):
        births, stats = self.decode(message(program="other-program"))
        self.assertEqual(births, [])
        self.assertEqual(stats["other_program_data"], 1)

    def test_padded_truncated_or_unknown_create_refuses(self):
        for raw in (payload() + b"x", payload()[:-1], b"unknown!"):
            with self.assertRaises((Refused, B9D.FreezeViolation)):
                self.decode(message(raw))

    def test_malformed_base64_refuses(self):
        data = message()
        data["params"]["result"]["value"]["logs"][1] = "Program data: !!!"
        with self.assertRaises(Refused):
            self.decode(data)

    def test_missing_err_is_not_inferred_success(self):
        data = message()
        del data["params"]["result"]["value"]["err"]
        with self.assertRaises(Refused):
            self.decode(data)

    def test_wrong_subscription_refuses(self):
        data = message()
        data["params"]["subscription"] = 8
        with self.assertRaises(Refused):
            self.decode(data)

    def test_broken_stack_and_truncation_refuse(self):
        for end in ("Program other-program success", "Log truncated", "not a program end"):
            data = message()
            data["params"]["result"]["value"]["logs"][-1] = end
            with self.assertRaises(Refused):
                self.decode(data)

    def test_raw_durable_before_decode_and_preserves_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            rec = Recorder(Path(directory) / "test.sqlite", max_bytes=8 * 1024 ** 2)
            data = message()
            raw = json.dumps(data).encode()
            wall, mono = time.time_ns(), time.monotonic_ns()
            seq = rec.append(raw, wall, mono)
            second = sqlite3.connect(rec.path)
            blob, status = second.execute("SELECT raw_zlib,decode_status FROM raw_frame").fetchone()
            second.close()
            self.assertEqual(zlib.decompress(blob), raw)
            self.assertEqual(status, "PENDING")
            births, stats = self.decode(data)
            rec.materialize(seq, births, stats)
            evidence = json.loads(rec.db.execute("SELECT observation_json FROM create_observation").fetchone()[0])
            self.assertEqual(evidence["received_unix_nanos"], wall)
            self.assertEqual(evidence["received_monotonic_nanos"], mono)
            self.assertEqual(evidence["status"], "NO_TRADE")
            rec.finish("TEST")

    def test_partial_decoded_batch_rolls_back_but_raw_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            rec = Recorder(Path(directory) / "test.sqlite", max_bytes=8 * 1024 ** 2)
            seq = rec.append(b"raw", time.time_ns(), time.monotonic_ns())
            births, stats = self.decode(message())
            with self.assertRaises(sqlite3.IntegrityError):
                rec.materialize(seq, births + births, stats)
            self.assertEqual(rec.db.execute("SELECT count(*) FROM create_observation").fetchone()[0], 0)
            self.assertEqual(rec.db.execute("SELECT decode_status FROM raw_frame").fetchone()[0], "PENDING")
            rec.finish("TEST")

    def test_existing_session_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            first = Recorder(path, max_bytes=8 * 1024 ** 2)
            first.finish("TEST")
            with self.assertRaises(Refused):
                Recorder(path, max_bytes=8 * 1024 ** 2)


if __name__ == "__main__":
    unittest.main()
