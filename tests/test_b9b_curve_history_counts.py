import importlib.util
import hashlib
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9b", ROOT / "scripts" / "b9b_curve_history_counts.py")
B9B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9B)


def rows(count, prefix="s", start_slot=100):
    return [
        {"signature": f"{prefix}{index}", "slot": start_slot - index,
         "blockTime": 1000 - index}
        for index in range(count)
    ]


def test_empty_history_is_complete_one_page():
    calls = []
    def fake(*args):
        calls.append(args)
        return []
    assert B9B.count_history("url", "curve", 10000, rpc_fn=fake) == (
        0, False, 1, None, None)
    assert calls[0][2][1] == {"limit": 1000, "commitment": "finalized"}


def test_short_page_is_complete():
    result = B9B.count_history("url", "curve", 10000, rpc_fn=lambda *_: rows(3))
    assert result == (3, False, 1, 98, 998)


def test_paginates_with_before_cursor():
    pages = [rows(1000, "a"), rows(2, "b", 10)]
    options = []
    def fake(_url, _method, params, _retries):
        options.append(params[1])
        return pages.pop(0)
    assert B9B.count_history("url", "curve", 10000, rpc_fn=fake)[:3] == (1002, False, 2)
    assert options[1]["before"] == "a999"


def test_cap_is_explicitly_censored():
    def fake(_url, _method, params, _retries):
        return rows(params[1]["limit"])
    assert B9B.count_history("url", "curve", 1500, rpc_fn=fake)[:3] == (1500, True, 2)


def test_missing_cursor_fails_visible():
    with pytest.raises(RuntimeError, match="cursor"):
        B9B.count_history(
            "url", "curve", 10,
            rpc_fn=lambda *_: [{"signature": None, "slot": 1, "blockTime": 2}])


def test_initialize_refuses_changed_cap(tmp_path):
    path = tmp_path / "counts.sqlite"
    connection = sqlite3.connect(path)
    B9B.initialize(connection, "source.sqlite", 100)
    with pytest.raises(RuntimeError, match="signature_cap"):
        B9B.initialize(connection, "source.sqlite", 200)
    connection.close()


def test_initialize_matching_completed_metadata_is_byte_immutable(tmp_path):
    path = tmp_path / "counts.sqlite"
    connection = sqlite3.connect(path)
    B9B.initialize(connection, "source.sqlite", 100)
    connection.close()
    before = hashlib.sha256(path.read_bytes()).digest()
    connection = sqlite3.connect(path)
    B9B.initialize(connection, "source.sqlite", 100)
    connection.close()
    assert hashlib.sha256(path.read_bytes()).digest() == before
