import hashlib
import importlib.util
import json
import pathlib
import struct
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "b7h", ROOT / "scripts" / "b7h_bonding_curve_recall.py")
B7H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B7H)
IDL = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
TYPES = {item["name"]: item for item in IDL["types"]}


def encode(type_name, value):
    if type_name == "string":
        raw = value.encode()
        return struct.pack("<I", len(raw)) + raw
    if type_name == "pubkey":
        return B7H.b7d.b58decode(value)
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


class RecallTests(unittest.TestCase):
    def test_extracts_only_successful_cohort_trade(self):
        mint = B7H.b7d.b58encode(bytes([7]) * 32)
        keys = iter(B7H.b7d.b58encode(bytes([i]) * 32) for i in range(8, 31))
        values = {}
        for field in TYPES["TradeEvent"]["type"]["fields"]:
            kind = field["type"]
            if field["name"] == "mint": value = mint
            elif kind == "pubkey": value = next(keys)
            elif kind == "string": value = "buy_v2"
            elif kind == "bool": value = False
            elif isinstance(kind, dict) and "option" in kind: value = None
            elif isinstance(kind, dict) and "vec" in kind: value = []
            else: value = 3
            values[field["name"]] = value
        disc = hashlib.sha256(b"event:TradeEvent").digest()[:8]
        body = b"".join(encode(f["type"], values[f["name"]])
                        for f in TYPES["TradeEvent"]["type"]["fields"])
        data = B7H.b7d.b58encode(B7H.b7d.EVENT_TAG + disc + body)
        transaction = {"transaction": {"signatures": ["sig"]}, "meta": {
            "err": None, "innerInstructions": [{"index": 2, "instructions": [{
                "programId": B7H.b7d.PUMP, "data": data}]}]}}
        rows, errors = B7H.extract_trade_events(
            10, {"transactions": [transaction]}, {mint}, TYPES, TYPES["TradeEvent"], disc)
        self.assertFalse(errors)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1:6], (mint, 10, 0, 2, 0))




class ThrottleHandlingTests(unittest.TestCase):
    """Behaviour added when the batched transport was replaced by bounded in-flight scheduling.

    Retrying a provider throttle burns quota and was measured to make things strictly worse:
    a prior run drove HTTP 403s from 60 to 148 while advancing exactly one slot. These tests pin
    the rule that a throttle is surfaced immediately, never retried.
    """

    def test_is_rate_limited_recognises_marker(self):
        self.assertTrue(B7H.is_rate_limited(f"{B7H.RATE_LIMIT_PREFIX} HTTP 403"))
        self.assertTrue(B7H.is_rate_limited(f"{B7H.RATE_LIMIT_PREFIX} HTTP 429"))

    def test_is_rate_limited_ignores_chain_and_transport_errors(self):
        # A 413 is a request-shape problem, not throttling: it must NOT stop the run.
        for other in (None, "", "HTTPError 413", "-32007: skipped", "ValueError: boom"):
            self.assertFalse(B7H.is_rate_limited(other), other)

    def _run_with_http_error(self, code, calls):
        import urllib.error

        def fake_urlopen(request, timeout=None):
            calls.append(code)
            raise urllib.error.HTTPError(
                "http://redacted", code, "throttled", hdrs=None, fp=None)

        original = B7H.urllib.request.urlopen
        B7H.urllib.request.urlopen = fake_urlopen
        try:
            return B7H.rpc_block_batch("http://redacted", [11, 12], retries=4)
        finally:
            B7H.urllib.request.urlopen = original

    def test_throttle_returns_immediately_without_retrying(self):
        for code in (403, 429):
            calls = []
            results = self._run_with_http_error(code, calls)
            self.assertEqual(len(calls), 1, f"HTTP {code} must not be retried")
            self.assertEqual([row[0] for row in results], [11, 12])
            for row in results:
                self.assertEqual(row[1], "error")
                self.assertTrue(B7H.is_rate_limited(row[3]), row[3])

    def test_non_throttle_http_error_still_retries(self):
        calls = []
        results = self._run_with_http_error(413, calls)
        self.assertEqual(len(calls), 4, "non-throttle errors keep the retry budget")
        self.assertFalse(B7H.is_rate_limited(results[0][3]))


class SchedulerTests(unittest.TestCase):
    """Pins the bounded in-flight scheduler that replaced submit-everything-then-read-in-order."""

    def test_never_exceeds_max_inflight(self):
        import threading
        live = {"now": 0, "peak": 0}
        lock = threading.Lock()

        def fetcher(url, slots, retries):
            with lock:
                live["now"] += 1
                live["peak"] = max(live["peak"], live["now"])
            time.sleep(0.01)
            with lock:
                live["now"] -= 1
            return [(slots[0], "retrieved", {}, None)]

        batches = [[n] for n in range(60)]
        seen = []
        done, stop = B7H.scan_batches(batches, workers=4, max_inflight=6, retries=1,
                                      rate_limit_stop=25, consume=seen.append, fetcher=fetcher)
        self.assertEqual(done, 60)
        self.assertIsNone(stop)
        self.assertEqual(len(seen), 60)
        self.assertLessEqual(live["peak"], 6, f"peak in-flight {live['peak']} exceeded bound")

    def test_stops_cleanly_on_sustained_throttling(self):
        attempted = []

        def fetcher(url, slots, retries):
            attempted.append(slots[0])
            return [(slots[0], "error", None, f"{B7H.RATE_LIMIT_PREFIX} HTTP 403")]

        batches = [[n] for n in range(500)]
        seen = []
        done, stop = B7H.scan_batches(batches, workers=2, max_inflight=2, retries=1,
                                      rate_limit_stop=5, consume=seen.append, fetcher=fetcher)
        self.assertIsNotNone(stop, "sustained throttling must stop the run")
        self.assertIn("rate-limited", stop)
        # The whole point: it must abandon the run, not grind through all 500 slots.
        self.assertLess(len(attempted), 500)
        self.assertLess(done, 500)

    def test_intermittent_throttling_does_not_stop_the_run(self):
        """A throttle followed by a success resets the counter — only sustained throttling halts."""
        def fetcher(url, slots, retries):
            slot = slots[0]
            if slot % 2 == 0:
                return [(slot, "error", None, f"{B7H.RATE_LIMIT_PREFIX} HTTP 429")]
            return [(slot, "retrieved", {}, None)]

        seen = []
        done, stop = B7H.scan_batches([[n] for n in range(40)], workers=1, max_inflight=1,
                                      retries=1, rate_limit_stop=5, consume=seen.append,
                                      fetcher=fetcher)
        self.assertIsNone(stop)
        self.assertEqual(done, 40)


class SchedulerValidationTests(unittest.TestCase):
    """Codex audit finding (4): a max_inflight below workers used to be silently raised."""

    def _noop_fetcher(self, url, slots, retries):
        return [(slots[0], "retrieved", {}, None)]

    def test_rejects_inflight_below_workers(self):
        with self.assertRaises(ValueError) as ctx:
            B7H.scan_batches([[1]], workers=4, max_inflight=2, retries=1, rate_limit_stop=5,
                             consume=lambda r: None, fetcher=self._noop_fetcher)
        self.assertIn("max_inflight", str(ctx.exception))

    def test_rejects_zero_workers(self):
        with self.assertRaises(ValueError):
            B7H.scan_batches([[1]], workers=0, max_inflight=4, retries=1, rate_limit_stop=5,
                             consume=lambda r: None, fetcher=self._noop_fetcher)

    def test_accepts_equal_bound(self):
        seen = []
        done, stop = B7H.scan_batches([[1], [2]], workers=2, max_inflight=2, retries=1,
                                      rate_limit_stop=5, consume=seen.append,
                                      fetcher=self._noop_fetcher)
        self.assertEqual((done, stop), (2, None))


if __name__ == "__main__":
    unittest.main()
