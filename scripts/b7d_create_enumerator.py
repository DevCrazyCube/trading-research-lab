#!/usr/bin/env python3
"""Enumerate Pump CreateEvents exhaustively over an explicit historical slot window.

The half-open window [start_slot, end_slot) is immutable for a database. Every requested slot is
recorded as retrieved, skipped, or error; errors make the run fail visibly. Events are decoded
from authoritative Anchor self-CPI inner instructions using the pinned IDL and stored with exact
ledger coordinates plus the original event payload. Re-running the same command resumes missing
or errored slots idempotently.

RPC URL comes only from SOLANA_RPC_URL and is never printed or persisted. Read-only: no signing
and no transaction submission.
"""
import argparse
import base64
import concurrent.futures as cf
import hashlib
import json
import os
import sqlite3
import struct
import tempfile
import time
import urllib.error
import urllib.request

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {char: index for index, char in enumerate(B58)}
SCHEMA_VERSION = "b7d-v2"


def b58decode(value):
    number = 0
    for char in value:
        number = number * 58 + B58_MAP[char]
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(value) - len(value.lstrip("1"))) + body


def b58encode(value):
    number = int.from_bytes(value, "big")
    out = ""
    while number:
        number, remainder = divmod(number, 58)
        out = B58[remainder] + out
    return "1" * (len(value) - len(value.lstrip(b"\0"))) + out


class Cursor:
    def __init__(self, data):
        self.data = data
        self.position = 0

    def take(self, size):
        if self.position + size > len(self.data):
            raise ValueError(
                f"short read at {self.position}: need {size}, have {len(self.data)-self.position}")
        value = self.data[self.position:self.position + size]
        self.position += size
        return value

    @property
    def remaining(self):
        return len(self.data) - self.position


PRIMITIVES = {
    "u8": (1, lambda value: value[0]),
    "i8": (1, lambda value: struct.unpack("<b", value)[0]),
    "u16": (2, lambda value: struct.unpack("<H", value)[0]),
    "i16": (2, lambda value: struct.unpack("<h", value)[0]),
    "u32": (4, lambda value: struct.unpack("<I", value)[0]),
    "i32": (4, lambda value: struct.unpack("<i", value)[0]),
    "u64": (8, lambda value: struct.unpack("<Q", value)[0]),
    "i64": (8, lambda value: struct.unpack("<q", value)[0]),
    "u128": (16, lambda value: int.from_bytes(value, "little")),
    "i128": (16, lambda value: int.from_bytes(value, "little", signed=True)),
    "bool": (1, lambda value: bool(value[0])),
    "pubkey": (32, b58encode),
}


def read_type(cursor, type_name, types):
    if isinstance(type_name, str):
        if type_name in PRIMITIVES:
            size, decoder = PRIMITIVES[type_name]
            return decoder(cursor.take(size))
        if type_name == "string":
            size = struct.unpack("<I", cursor.take(4))[0]
            return cursor.take(size).decode("utf-8", "strict")
        raise ValueError(f"unsupported primitive {type_name}")
    if "vec" in type_name:
        size = struct.unpack("<I", cursor.take(4))[0]
        return [read_type(cursor, type_name["vec"], types) for _ in range(size)]
    if "option" in type_name:
        tag = cursor.take(1)[0]
        if tag not in (0, 1):
            raise ValueError(f"invalid option tag {tag}")
        return read_type(cursor, type_name["option"], types) if tag else None
    if "array" in type_name:
        inner, size = type_name["array"]
        return [read_type(cursor, inner, types) for _ in range(size)]
    if "defined" in type_name:
        defined = type_name["defined"]
        name = defined["name"] if isinstance(defined, dict) else defined
        return read_struct(cursor, types[name], types)
    raise ValueError(f"unsupported type {type_name}")


def read_struct(cursor, definition, types):
    return {
        field["name"]: read_type(cursor, field["type"], types)
        for field in definition["type"]["fields"]
    }


def decode_create_payload(payload, create_disc, create_type, types):
    if payload[:8] != create_disc:
        return None
    cursor = Cursor(payload[8:])
    event = read_struct(cursor, create_type, types)
    if cursor.remaining:
        raise ValueError(f"CreateEvent has {cursor.remaining} trailing bytes")
    return event


def rpc_block(url, slot, retries):
    params = [slot, {"encoding": "jsonParsed", "transactionDetails": "full", "rewards": False,
                     "maxSupportedTransactionVersion": 0}]
    body = json.dumps({"jsonrpc": "2.0", "id": slot, "method": "getBlock", "params": params}).encode()
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read())
            if "error" not in result:
                if result.get("result") is None:
                    return slot, "skipped", None, "null result"
                return slot, "retrieved", result["result"], None
            error = result["error"]
            if error.get("code") in (-32007, -32009):
                return slot, "skipped", None, f"{error.get('code')}: {error.get('message')}"
            last_error = f"{error.get('code')}: {error.get('message')}"
        except urllib.error.HTTPError as error:
            last_error = f"HTTP {error.code}"
            if error.code != 429:
                break
        except Exception as error:  # noqa: BLE001
            last_error = f"{type(error).__name__}: {error}"
        if attempt + 1 < retries:
            time.sleep(min(0.5 * 2 ** attempt, 8))
    return slot, "error", None, last_error or "unknown RPC failure"


def rpc_produced_slots(url, start_slot, end_slot, retries):
    """Return the validator's produced-block list for an inclusive range."""
    body = json.dumps({
        "jsonrpc": "2.0", "id": start_slot, "method": "getBlocks",
        "params": [start_slot, end_slot, {"commitment": "finalized"}],
    }).encode()
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read())
            if "error" not in result:
                return set(result["result"]), None
            last_error = f"{result['error'].get('code')}: {result['error'].get('message')}"
        except Exception as error:  # noqa: BLE001
            last_error = f"{type(error).__name__}: {error}"
        if attempt + 1 < retries:
            time.sleep(min(0.5 * 2 ** attempt, 8))
    return None, last_error or "unknown getBlocks failure"


def verify_skipped_slots(connection, url, retries):
    """Resolve getBlock's '-32009 skipped or missing' ambiguity through getBlocks."""
    candidates = [row[0] for row in connection.execute(
        "SELECT slot FROM slot_scan WHERE status = 'skipped' ORDER BY slot")]
    if not candidates:
        return
    with connection:
        connection.executemany("UPDATE slot_scan SET status='skip_unverified' WHERE slot=?",
                               [(slot,) for slot in candidates])
    for chunk_start in range(min(candidates), max(candidates) + 1, 500000):
        chunk_end = min(chunk_start + 499999, max(candidates))
        in_chunk = [slot for slot in candidates if chunk_start <= slot <= chunk_end]
        produced, error = rpc_produced_slots(url, chunk_start, chunk_end, retries)
        with connection:
            if produced is None:
                connection.executemany(
                    "UPDATE slot_scan SET error = error || '; getBlocks failed: ' || ? WHERE slot=?",
                    [(error, slot) for slot in in_chunk])
                continue
            for slot in in_chunk:
                if slot in produced:
                    connection.execute(
                        "UPDATE slot_scan SET status='error', error=error || "
                        "'; getBlocks lists produced slot but getBlock unavailable' WHERE slot=?",
                        (slot,))
                else:
                    connection.execute(
                        "UPDATE slot_scan SET status='skipped', error=error || "
                        "'; absence verified by getBlocks' WHERE slot=?", (slot,))


def extract_block(slot, block, create_disc, create_type, types, create_instruction_discs):
    events = []
    decode_errors = []
    pump_transactions = 0
    create_instructions = 0
    for transaction_index, transaction in enumerate(block.get("transactions", [])):
        meta = transaction.get("meta") or {}
        message = transaction["transaction"]["message"]
        touches_pump = any(ix.get("programId") == PUMP for ix in message.get("instructions", []))
        touches_pump |= any(
            ix.get("programId") == PUMP
            for group in meta.get("innerInstructions") or []
            for ix in group.get("instructions", [])
        )
        pump_transactions += bool(touches_pump)
        if meta.get("err") is not None:
            continue
        signature = transaction["transaction"]["signatures"][0]
        for instruction in message.get("instructions", []):
            if instruction.get("programId") == PUMP and instruction.get("data"):
                raw = b58decode(instruction["data"])
                create_instructions += raw[:8] in create_instruction_discs
        for group in meta.get("innerInstructions") or []:
            outer_index = group["index"]
            for inner_index, instruction in enumerate(group.get("instructions", [])):
                if instruction.get("programId") != PUMP or not instruction.get("data"):
                    continue
                raw = b58decode(instruction["data"])
                if raw[:8] in create_instruction_discs:
                    create_instructions += 1
                if len(raw) < 16 or raw[:8] != EVENT_TAG or raw[8:16] != create_disc:
                    continue
                payload = raw[8:]
                try:
                    fields = decode_create_payload(payload, create_disc, create_type, types)
                except Exception as error:  # noqa: BLE001
                    decode_errors.append({
                        "slot": slot, "transaction_index": transaction_index,
                        "outer_instruction_index": outer_index,
                        "inner_instruction_index": inner_index, "signature": signature,
                        "error": f"{type(error).__name__}: {error}",
                    })
                    continue
                events.append({
                    "slot": slot, "transaction_index": transaction_index,
                    "outer_instruction_index": outer_index,
                    "inner_instruction_index": inner_index, "signature": signature,
                    "block_time": block.get("blockTime"), "fields": fields,
                    "event_payload_base64": base64.b64encode(payload).decode(),
                })
    return events, decode_errors, pump_transactions, create_instructions


def connect_database(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS slot_scan (
            slot INTEGER PRIMARY KEY, status TEXT NOT NULL,
            blockhash TEXT, previous_blockhash TEXT, parent_slot INTEGER, block_time INTEGER,
            transaction_count INTEGER, pump_transaction_count INTEGER,
            create_instruction_count INTEGER,
            error TEXT, scanned_at_unix REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS create_event (
            slot INTEGER NOT NULL, transaction_index INTEGER NOT NULL,
            outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
            signature TEXT NOT NULL, block_time INTEGER, mint TEXT NOT NULL,
            bonding_curve TEXT NOT NULL, creator TEXT, user TEXT,
            is_mayhem_mode INTEGER, is_cashback_enabled INTEGER, quote_mint TEXT,
            fields_json TEXT NOT NULL, event_payload_base64 TEXT NOT NULL,
            PRIMARY KEY (slot, transaction_index, outer_instruction_index, inner_instruction_index)
        );
        CREATE TABLE IF NOT EXISTS decode_error (
            slot INTEGER NOT NULL, transaction_index INTEGER NOT NULL,
            outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
            signature TEXT NOT NULL, error TEXT NOT NULL,
            PRIMARY KEY (slot, transaction_index, outer_instruction_index, inner_instruction_index)
        );
    """)
    return connection


def initialize_metadata(connection, expected):
    present = dict(connection.execute("SELECT key, value FROM metadata"))
    if present:
        mismatches = {key: (present.get(key), value) for key, value in expected.items()
                      if present.get(key) != value}
        if mismatches:
            raise RuntimeError(f"database metadata mismatch: {mismatches}")
        return
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", expected.items())
    connection.commit()


def store_result(connection, slot, status, block, error, create_disc, create_type, types,
                 create_instruction_discs):
    events, decode_errors, pump_transactions, create_instructions = [], [], 0, 0
    if status == "retrieved":
        events, decode_errors, pump_transactions, create_instructions = extract_block(
            slot, block, create_disc, create_type, types, create_instruction_discs)
        if decode_errors:
            status = "decode_error"
            error = f"{len(decode_errors)} CreateEvent decode failure(s)"
        elif create_instructions != len(events):
            status = "reconciliation_error"
            error = (f"successful create instructions={create_instructions}, "
                     f"CreateEvents={len(events)}")
    with connection:
        connection.execute("DELETE FROM create_event WHERE slot = ?", (slot,))
        connection.execute("DELETE FROM decode_error WHERE slot = ?", (slot,))
        for event in events:
            fields = event["fields"]
            connection.execute("""
                INSERT INTO create_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event["slot"], event["transaction_index"], event["outer_instruction_index"],
                event["inner_instruction_index"], event["signature"], event["block_time"],
                fields["mint"], fields["bonding_curve"], fields.get("creator"), fields.get("user"),
                fields.get("is_mayhem_mode"), fields.get("is_cashback_enabled"),
                fields.get("quote_mint"), json.dumps(fields, sort_keys=True, separators=(",", ":")),
                event["event_payload_base64"],
            ))
        for row in decode_errors:
            connection.execute("INSERT INTO decode_error VALUES (?, ?, ?, ?, ?, ?)", (
                row["slot"], row["transaction_index"], row["outer_instruction_index"],
                row["inner_instruction_index"], row["signature"], row["error"],
            ))
        connection.execute("""
            INSERT OR REPLACE INTO slot_scan VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            slot, status, (block or {}).get("blockhash"), (block or {}).get("previousBlockhash"),
            (block or {}).get("parentSlot"), (block or {}).get("blockTime"),
            len((block or {}).get("transactions", [])) if block else None,
            pump_transactions if block else None, create_instructions if block else None,
            error, time.time(),
        ))


def export_jsonl(connection, path):
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    start, end = int(metadata["start_slot"]), int(metadata["end_slot_exclusive"])
    counts = dict(connection.execute("SELECT status, COUNT(*) FROM slot_scan GROUP BY status"))
    accounted = sum(counts.values())
    bad = sum(count for status, count in counts.items() if status not in ("retrieved", "skipped"))
    if accounted != end - start or bad:
        raise RuntimeError(f"cannot export incomplete window: accounted={accounted}/{end-start}, {counts}")
    destination = os.path.abspath(path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(destination), delete=False) as handle:
        for row in connection.execute("""
            SELECT slot, transaction_index, outer_instruction_index, inner_instruction_index,
                   signature, block_time, fields_json, event_payload_base64
            FROM create_event ORDER BY slot, transaction_index,
                 outer_instruction_index, inner_instruction_index
        """):
            fields = json.loads(row[6])
            output = {
                "slot": row[0], "transaction_index": row[1],
                "outer_instruction_index": row[2], "inner_instruction_index": row[3],
                "signature": row[4], "block_time": row[5], **fields,
                "event_payload_base64": row[7],
            }
            handle.write(json.dumps(output, sort_keys=True, separators=(",", ":")) + "\n")
        temporary = handle.name
    os.replace(temporary, destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-slot", type=int, required=True)
    parser.add_argument("--end-slot", type=int, required=True, help="exclusive upper slot")
    parser.add_argument("--database", required=True)
    parser.add_argument("--export-jsonl")
    parser.add_argument("--idl", default="research/pump_idl_9c82f61.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=6)
    args = parser.parse_args()
    if args.end_slot <= args.start_slot:
        parser.error("--end-slot must exceed --start-slot")
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")

    with open(args.idl, "rb") as handle:
        idl_bytes = handle.read()
    idl = json.loads(idl_bytes)
    types = {item["name"]: item for item in idl["types"]}
    create_type = types["CreateEvent"]
    create_disc = hashlib.sha256(b"event:CreateEvent").digest()[:8]
    create_instruction_discs = {
        bytes(instruction["discriminator"])
        for instruction in idl["instructions"] if instruction["name"] in ("create", "create_v2")
    }
    url = os.environ.get("SOLANA_RPC_URL", DEFAULT_RPC)
    endpoint_ref = "public-mainnet" if url == DEFAULT_RPC else "configured-mainnet"
    connection = connect_database(args.database)
    initialize_metadata(connection, {
        "schema_version": SCHEMA_VERSION,
        "start_slot": str(args.start_slot),
        "end_slot_exclusive": str(args.end_slot),
        "program_id": PUMP,
        "idl_sha256": hashlib.sha256(idl_bytes).hexdigest(),
        "endpoint_ref": endpoint_ref,
    })
    completed = {row[0] for row in connection.execute(
        "SELECT slot FROM slot_scan WHERE status IN ('retrieved', 'skipped')")}
    pending = [slot for slot in range(args.start_slot, args.end_slot) if slot not in completed]
    print(f"window=[{args.start_slot},{args.end_slot}) endpoint={endpoint_ref} "
          f"already_complete={len(completed)} pending={len(pending)}", flush=True)

    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = executor.map(lambda slot: rpc_block(url, slot, args.retries), pending)
        for index, (slot, status, block, error) in enumerate(futures, 1):
            store_result(connection, slot, status, block, error, create_disc, create_type, types,
                         create_instruction_discs)
            if index % 25 == 0 or status not in ("retrieved", "skipped") or index == len(pending):
                events = connection.execute("SELECT COUNT(*) FROM create_event").fetchone()[0]
                print(f"{index}/{len(pending)} slot={slot} status={status} creates={events}",
                      flush=True)

    verify_skipped_slots(connection, url, args.retries)

    counts = dict(connection.execute("SELECT status, COUNT(*) FROM slot_scan GROUP BY status"))
    creates = connection.execute("SELECT COUNT(*) FROM create_event").fetchone()[0]
    decode_errors = connection.execute("SELECT COUNT(*) FROM decode_error").fetchone()[0]
    print(f"slot_status={counts} creates={creates} decode_errors={decode_errors}")
    if args.export_jsonl:
        export_jsonl(connection, args.export_jsonl)
        print(f"exported={args.export_jsonl}")
    connection.close()
    bad = sum(count for status, count in counts.items() if status not in ("retrieved", "skipped"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
