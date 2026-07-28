import hashlib
import importlib.util
import json
import pathlib
import struct
import tempfile
import unittest


ROOT = pathlib.Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "b7d_create_enumerator.py"
SPEC = importlib.util.spec_from_file_location("b7d", SCRIPT)
B7D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B7D)
IDL = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
TYPES = {item["name"]: item for item in IDL["types"]}
CREATE_IX_DISC = bytes(next(item["discriminator"] for item in IDL["instructions"]
                            if item["name"] == "create_v2"))


def encode_type(type_name, value):
    if type_name == "string":
        raw = value.encode()
        return struct.pack("<I", len(raw)) + raw
    if type_name == "pubkey":
        return B7D.b58decode(value)
    if type_name == "bool":
        return bytes([value])
    if type_name in ("u8", "i8"):
        return int(value).to_bytes(1, "little", signed=type_name.startswith("i"))
    if type_name[0] in "ui" and type_name[1:].isdigit():
        return int(value).to_bytes(int(type_name[1:]) // 8, "little",
                                   signed=type_name.startswith("i"))
    if isinstance(type_name, dict) and "option" in type_name:
        return b"\0" if value is None else b"\1" + encode_type(type_name["option"], value)
    raise AssertionError(f"test encoder lacks {type_name}")


def create_fields():
    fields = {}
    pubkeys = iter([B7D.b58encode(bytes([index]) * 32) for index in range(1, 16)])
    for field in TYPES["CreateEvent"]["type"]["fields"]:
        type_name = field["type"]
        if type_name == "string":
            value = field["name"]
        elif type_name == "pubkey":
            value = next(pubkeys)
        elif type_name == "bool":
            value = field["name"] == "is_cashback_enabled"
        elif isinstance(type_name, dict) and "option" in type_name:
            value = None
        else:
            value = 42
        fields[field["name"]] = value
    return fields


def create_payload(fields):
    discriminator = hashlib.sha256(b"event:CreateEvent").digest()[:8]
    body = b"".join(encode_type(field["type"], fields[field["name"]])
                    for field in TYPES["CreateEvent"]["type"]["fields"])
    return discriminator + body


class CreateEnumeratorTests(unittest.TestCase):
    def test_exact_idl_decode(self):
        fields = create_fields()
        payload = create_payload(fields)
        decoded = B7D.decode_create_payload(
            payload, payload[:8], TYPES["CreateEvent"], TYPES)
        self.assertEqual(decoded, fields)

    def test_extracts_coordinates_and_export_requires_complete_window(self):
        fields = create_fields()
        payload = create_payload(fields)
        instruction = B7D.b58encode(B7D.EVENT_TAG + payload)
        block = {
            "blockhash": "block", "previousBlockhash": "previous", "parentSlot": 9,
            "blockTime": 1234,
            "transactions": [{
                "transaction": {"signatures": ["signature"], "message": {"instructions": [
                    {"programId": B7D.PUMP, "data": B7D.b58encode(CREATE_IX_DISC)}
                ]}},
                "meta": {"err": None, "innerInstructions": [{
                    "index": 3, "instructions": [{"programId": B7D.PUMP, "data": instruction}]
                }]},
            }],
        }
        events, errors, pump_transactions, create_instructions = B7D.extract_block(
            10, block, payload[:8], TYPES["CreateEvent"], TYPES, {CREATE_IX_DISC})
        self.assertFalse(errors)
        self.assertEqual(pump_transactions, 1)
        self.assertEqual(create_instructions, 1)
        self.assertEqual((events[0]["slot"], events[0]["transaction_index"],
                          events[0]["outer_instruction_index"],
                          events[0]["inner_instruction_index"]), (10, 0, 3, 0))

        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "events.sqlite"
            output = pathlib.Path(directory) / "events.jsonl"
            connection = B7D.connect_database(database)
            B7D.initialize_metadata(connection, {
                "schema_version": B7D.SCHEMA_VERSION, "start_slot": "10",
                "end_slot_exclusive": "12", "program_id": B7D.PUMP,
                "idl_sha256": "test", "endpoint_ref": "test",
            })
            B7D.store_result(connection, 10, "retrieved", block, None, payload[:8],
                             TYPES["CreateEvent"], TYPES, {CREATE_IX_DISC})
            with self.assertRaisesRegex(RuntimeError, "incomplete window"):
                B7D.export_jsonl(connection, output)
            B7D.store_result(connection, 11, "skipped", None, "skipped", payload[:8],
                             TYPES["CreateEvent"], TYPES, set())
            B7D.export_jsonl(connection, output)
            row = json.loads(output.read_text().strip())
            self.assertEqual(row["mint"], fields["mint"])
            self.assertEqual(row["outer_instruction_index"], 3)


if __name__ == "__main__":
    unittest.main()
