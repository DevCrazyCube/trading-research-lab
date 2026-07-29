import hashlib
import importlib.util
import json
import sqlite3
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9c", ROOT / "scripts" / "b9c_signature_inventory.py")
B9C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9C)


def test_classify_slot_envelope():
    assert B9C.classify({"slot": 9}, 10, 20) == "before_launch"
    assert B9C.classify({"slot": 10}, 10, 20) == "in_window"
    assert B9C.classify({"slot": 20}, 10, 20) == "in_window"
    assert B9C.classify({"slot": 21}, 10, 20) == "after_cutoff"
    assert B9C.classify({"slot": None}, 10, 20) == "unknown"


def test_normalize_preserves_error_and_coordinates():
    page = [{"signature": "sig", "slot": 15, "blockTime": 123, "err": {"x": 1},
             "memo": "m", "confirmationStatus": "finalized"}]
    row = B9C.normalize_page("curve", 2, page, 10, 20)[0]
    assert row == ("curve", "sig", 15, 123, '{"x":1}', "m", "finalized", 2, 0,
                   "in_window")


def test_normalize_missing_signature_fails_visible():
    with pytest.raises(RuntimeError, match="missing signature"):
        B9C.normalize_page("curve", 0, [{"slot": 1}], 1, 2)


def test_request_key_is_canonical():
    left = B9C.request_key("m", [{"b": 2, "a": 1}])
    right = B9C.request_key("m", [{"a": 1, "b": 2}])
    assert left == right


def test_store_raw_preserves_exact_bytes(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    raw = b'{"jsonrpc":"2.0","result":[ ] ,"id":1}'
    B9C.store_raw(db, "key", "method", [1], raw, "curve", 0)
    compressed, digest = db.execute(
        "SELECT raw_zlib,response_sha256 FROM raw_rpc_response").fetchone()
    assert zlib.decompress(compressed) == raw
    assert digest == hashlib.sha256(raw).hexdigest()
    db.close()


def test_schema_indexes_raw_page_coordinates(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    indexes = {row[1] for row in db.execute("PRAGMA index_list(signature_observation)")}
    assert "signature_observation_page_coordinate" in indexes
    db.close()


def test_initialize_matching_metadata_is_idempotent(tmp_path):
    path = tmp_path / "x.sqlite"
    members = [("mint", "curve", 10)]
    db = B9C.connect(path)
    B9C.initialize(db, "source", "hash", members, 40)
    assert dict(db.execute("SELECT key,value FROM metadata"))["cutoff_time"] == str(B9C.CUTOFF_TIME)
    before = list(db.iterdump())
    B9C.initialize(db, "source", "hash", members, 40)
    assert list(db.iterdump()) == before
    db.close()


def test_initialize_refuses_source_hash_change(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.initialize(db, "source", "one", [("mint", "curve", 10)], 40)
    with pytest.raises(RuntimeError, match="source_sha256"):
        B9C.initialize(db, "source", "two", [("mint", "curve", 10)], 40)
    db.close()


def test_preserved_request_replays_and_verifies_hash(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    params = [1]
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": 99}).encode()
    key = B9C.request_key("getBlockTime", params)
    B9C.store_raw(db, key, "getBlockTime", params, raw)
    got_key, got_raw, result, stored = B9C.preserved_request(
        db, "unused", "getBlockTime", params, 1)
    assert (got_key, got_raw, result, stored) == (key, raw, 99, True)
    db.execute("UPDATE raw_rpc_response SET response_sha256='bad'")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        B9C.preserved_request(db, "unused", "getBlockTime", params, 1)
    db.close()


def test_verify_raw_replay_detects_normalized_mismatch(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    db.executemany("INSERT INTO metadata VALUES (?,?)", [
        ("cutoff_slot", "20"), ("cutoff_time", str(B9C.CUTOFF_TIME))])
    db.execute("INSERT INTO curve_scan(mint,bonding_curve,launch_slot) VALUES ('m','c',10)")
    page = [{"signature": "s", "slot": 15, "blockTime": 1, "err": None,
             "memo": None, "confirmationStatus": "finalized"}]
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": page}).encode()
    B9C.store_raw(db, "key", "getSignaturesForAddress", ["c", {}], raw, "c", 0)
    db.executemany("INSERT INTO signature_observation VALUES (?,?,?,?,?,?,?,?,?,?)",
                   B9C.normalize_page("c", 0, page, 10, 20))
    assert B9C.verify_raw_replay(db) == (1, 1)
    db.execute("UPDATE signature_observation SET time_class='after_cutoff'")
    with pytest.raises(RuntimeError, match="normalized replay mismatch"):
        B9C.verify_raw_replay(db)
    db.close()
