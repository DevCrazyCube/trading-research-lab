import hashlib
import importlib.util
import json
import pathlib
import struct
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "b7e_lifecycle_reconstruct.py"
SPEC = importlib.util.spec_from_file_location("b7e", SCRIPT)
B7E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B7E)
IDL = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
TYPES = {item["name"]: item for item in IDL["types"]}


def encode(type_name, value):
    if type_name == "string":
        raw = value.encode()
        return struct.pack("<I", len(raw)) + raw
    if type_name == "pubkey":
        return B7E.b7d.b58decode(value)
    if type_name == "bool":
        return bytes([value])
    if type_name in ("u8", "i8"):
        return int(value).to_bytes(1, "little", signed=type_name.startswith("i"))
    if isinstance(type_name, str) and type_name[0] in "ui" and type_name[1:].isdigit():
        return int(value).to_bytes(int(type_name[1:]) // 8, "little",
                                   signed=type_name.startswith("i"))
    if isinstance(type_name, dict) and "option" in type_name:
        return b"\0" if value is None else b"\1" + encode(type_name["option"], value)
    if isinstance(type_name, dict) and "vec" in type_name:
        return struct.pack("<I", len(value)) + b"".join(
            encode(type_name["vec"], item) for item in value)
    raise AssertionError(type_name)


class LifecycleTests(unittest.TestCase):
    def test_history_respects_launch_and_cutoff(self):
        page = [
            {"signature": "future", "slot": 201, "blockTime": 4, "err": None},
            {"signature": "inside", "slot": 150, "blockTime": 3, "err": None},
            {"signature": "launch", "slot": 100, "blockTime": 2, "err": None},
            {"signature": "before", "slot": 99, "blockTime": 1, "err": None},
        ]
        with mock.patch.object(B7E, "rpc", return_value=(page, None)):
            rows, status, pages, examined, error = B7E.address_history(
                "url", "address", 100, 200, 1000, 1)
        self.assertEqual([row["signature"] for row in rows], ["inside", "launch"])
        self.assertEqual((status, pages, examined, error), ("complete", 1, 4, None))

    def test_decodes_only_expected_mint_trade_event(self):
        expected_mint = B7E.b7d.b58encode(bytes([7]) * 32)
        other_keys = iter(B7E.b7d.b58encode(bytes([index]) * 32) for index in range(8, 30))
        fields = {}
        for field in TYPES["TradeEvent"]["type"]["fields"]:
            type_name = field["type"]
            if field["name"] == "mint":
                value = expected_mint
            elif type_name == "pubkey":
                value = next(other_keys)
            elif type_name == "string":
                value = "buy_v2"
            elif type_name == "bool":
                value = False
            elif isinstance(type_name, dict) and "option" in type_name:
                value = None
            elif isinstance(type_name, dict) and "vec" in type_name:
                value = []
            else:
                value = 11
            fields[field["name"]] = value
        discriminator = hashlib.sha256(b"event:TradeEvent").digest()[:8]
        body = b"".join(encode(field["type"], fields[field["name"]])
                        for field in TYPES["TradeEvent"]["type"]["fields"])
        instruction = B7E.b7d.b58encode(B7E.b7d.EVENT_TAG + discriminator + body)
        transaction = {"meta": {"innerInstructions": [{
            "index": 2, "instructions": [{"programId": B7E.b7d.PUMP, "data": instruction}]
        }]}}
        events, errors = B7E.decode_transaction(
            json.dumps(transaction).encode(), expected_mint,
            {discriminator: "TradeEvent"}, {"TradeEvent": TYPES["TradeEvent"]}, TYPES)
        self.assertFalse(errors)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "TradeEvent")
        self.assertEqual(events[0][4], fields)


if __name__ == "__main__":
    unittest.main()
