"""B15i tests. Every refusal path is driven, not asserted about.

The properties that matter here are ordering properties — raw before enqueue, durable before
worker, never-fetch-after-the-deadline — and an ordering property that is only intended is an
ordering property that is not there. Each one is provoked with a fixture that would pass if the
order were wrong.
"""
import base64
import importlib.util
import json
import pathlib
import queue
import sys
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


B15I = _load("b15i_processed_feed", "b15i_processed_feed.py")
PILOT, B15F = B15I.PILOT, B15I.B15F

FIXTURES = _load("b15a_shadow_fixtures", "b15a_shadow_fixtures.py")

PUMP_PROGRAM = PILOT.PUMP_PROGRAM
SIGNATURE = "Sig111111111111111111111111111111111111111"


def _bonding_curve_bytes(virtual_quote=30_000_000_000, complete=False, discriminator=None):
    """A BondingCurve account under the PINNED layout, not a hand-written blob.

    Built by walking the IDL so the fixture cannot drift from the decoder it exercises. A
    hand-rolled byte string keeps passing after the layout changes shape, which is the drift the
    decode path exists to catch.
    """
    _b7d, _discriminator, _create_type, types = PILOT.load_pinned_create_type()
    raw = bytearray(B15F.BONDING_CURVE_DISCRIMINATOR if discriminator is None else discriminator)
    for field in types["BondingCurve"]["type"]["fields"]:
        if field["name"] == "virtual_quote_reserves":
            raw += virtual_quote.to_bytes(8, "little")
        elif field["name"] == "complete":
            raw += b"\x01" if complete else b"\x00"
        else:
            raw += FIXTURES._encode(field["type"], types)
    return bytes(raw)


def _frame(slot, signature=SIGNATURE, err=None, logs=None):
    return json.dumps({
        "jsonrpc": "2.0", "method": "logsNotification",
        "params": {"result": {"context": {"slot": slot},
                              "value": {"signature": signature, "err": err,
                                        "logs": logs if logs is not None else []}},
                   "subscription": 1}})


def _create_frame(slot, signature=SIGNATURE):
    payload = FIXTURES.create_payload()
    return _frame(slot, signature,
                  logs=[f"{PILOT.PROGRAM_DATA_PREFIX}{base64.b64encode(payload).decode()}"])


class Harness:
    """Feed handler wiring with no socket and no network."""

    def __init__(self, tmp, activation=100, max_depth=B15I.MAX_QUEUE_DEPTH):
        self.tmp = pathlib.Path(tmp)
        self.connection = B15I.open_database(self.tmp / "db.sqlite")
        self.raw = B15I.RawLog(self.tmp / "raw.jsonl")
        self.queue = queue.Queue(maxsize=max_depth)
        self.lock = threading.Lock()
        self.counts = {"frames": 0, "launches": 0, "already_passed": 0, "overflow": 0,
                       "captured": 0, "refused": 0, "pre_activation": 0, "worker_errors": 0}
        b7d, discriminator, create_type, types = PILOT.load_pinned_create_type()
        self.decoder = {"b7d": b7d, "discriminator": discriminator,
                        "create_type": create_type, "types": types}
        self.document = {"activation": {"activation_slot": activation},
                         "checkpoint_geometry": {"delays": [1, 2, 4], "max_lateness_slots": 150}}

    def feed(self, message):
        B15I.handle_frame(message, self.decoder, self.raw, self.connection, self.queue,
                          self.document, self.counts, self.lock)

    def rows(self, table):
        return self.connection.execute(f"SELECT * FROM {table}").fetchall()


class TestGates(unittest.TestCase):
    def test_preregistration_is_pinned(self):
        document = B15I.verify_preregistration()
        self.assertEqual(document["preregistration_id"], "B15I_PROCESSED_FEED_V1")
        self.assertTrue(document["committed_before_connecting"])

    def test_a_tampered_preregistration_refuses(self):
        altered = self.tmp = pathlib.Path(self.id().split(".")[-1] + ".json")
        try:
            document = json.loads(B15I.PREREG_PATH.read_bytes())
            document["checkpoint_geometry"]["max_lateness_slots"] = 10_000
            altered.write_text(json.dumps(document))
            with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
                B15I.verify_preregistration(altered)
            self.assertIn("pinned", str(caught.exception))
        finally:
            altered.unlink(missing_ok=True)

    def test_an_unreadable_preregistration_refuses(self):
        with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
            B15I.verify_preregistration(ROOT / "research" / "does_not_exist.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_the_feed_handler_contains_no_rpc_call(self):
        self.assertTrue(B15I.assert_feed_thread_does_not_call_rpc())

    def test_an_rpc_call_in_the_feed_handler_is_caught(self):
        """The check must fire on a handler that would block. Proven by giving it one."""
        source = B15I.PREREG_PATH.parent.parent / "scripts" / "b15i_processed_feed.py"
        poisoned = pathlib.Path("poisoned_handler.py")
        try:
            text = source.read_text().replace(
                "    received_wall, received_mono = time.time(), time.monotonic_ns()",
                "    urlopen('http://x')\n"
                "    received_wall, received_mono = time.time(), time.monotonic_ns()", 1)
            poisoned.write_text(text)
            with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
                B15I.assert_feed_thread_does_not_call_rpc(poisoned)
            self.assertIn("urlopen", str(caught.exception))
        finally:
            poisoned.unlink(missing_ok=True)

    def test_a_missing_feed_handler_is_caught(self):
        stub = pathlib.Path("no_handler.py")
        try:
            stub.write_text("def other():\n    pass\n")
            with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
                B15I.assert_feed_thread_does_not_call_rpc(stub)
            self.assertIn("handle_frame is missing", str(caught.exception))
        finally:
            stub.unlink(missing_ok=True)

    def test_no_execution_surface(self):
        self.assertTrue(B15I.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        poisoned = pathlib.Path("poisoned_surface.py")
        try:
            poisoned.write_text("EXECUTION_SURFACE_TOKENS = ()\nx = 'sendTransaction'\n")
            with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
                B15I.assert_no_execution_surface(poisoned)
            self.assertIn("sendTransaction", str(caught.exception))
        finally:
            poisoned.unlink(missing_ok=True)

    def test_writing_into_another_worker_is_refused(self):
        for other in ("b15a", "b15h", "b11a"):
            with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
                B15I.assert_isolated(ROOT / "research" / other)
            self.assertIn("read-only here", str(caught.exception))

    def test_a_work_directory_that_is_not_b15i_is_refused(self):
        with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
            B15I.assert_isolated(ROOT / "research" / "elsewhere")
        self.assertIn("must be .../b15i", str(caught.exception))

    def test_a_float_is_refused(self):
        with self.assertRaises(B15I.ProcessedFeedRefused):
            B15I.assert_no_float({"reserves": 1.5})
        self.assertTrue(B15I.assert_no_float({"reserves": 15}))


class TestTargets(unittest.TestCase):
    def test_lead_slots(self):
        self.assertEqual(B15I.target_lead_slots(104, 100), 4)
        self.assertEqual(B15I.target_lead_slots(101, 101), 0)
        self.assertEqual(B15I.target_lead_slots(101, 105), -4)

    def test_a_passed_target_is_refused(self):
        for observed in (101, 105):
            with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
                B15I.assert_target_future(101, observed)
            self.assertIn(B15I.Q_TARGET_ALREADY_PASSED, str(caught.exception))
        self.assertTrue(B15I.assert_target_future(102, 101))

    def test_the_lateness_tolerance_is_b15fs_and_cannot_be_widened_here(self):
        document = B15I.verify_preregistration()
        checkpoint = B15F.verify_preregistration()
        self.assertTrue(B15I.assert_lateness_tolerance_unchanged(document, checkpoint))
        self.assertEqual(document["checkpoint_geometry"]["max_lateness_slots"], 150)
        widened = json.loads(json.dumps(document))
        widened["checkpoint_geometry"]["max_lateness_slots"] = 10_000
        with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
            B15I.assert_lateness_tolerance_unchanged(widened, checkpoint)
        self.assertIn("not widened here", str(caught.exception))

    def test_activation_is_strict(self):
        for t0 in (None, 99, 100):
            with self.assertRaises(B15I.ProcessedFeedRefused) as caught:
                B15I.assert_after_activation(t0, 100)
            self.assertIn(B15I.Q_PRE_ACTIVATION, str(caught.exception))
        self.assertTrue(B15I.assert_after_activation(101, 100))


class TestFeedHandler(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(f"b15i_tmp_{self.id().split('.')[-1]}")
        self.directory.mkdir(exist_ok=True)
        self.harness = Harness(self.directory)

    def tearDown(self):
        self.harness.raw.close()
        self.harness.connection.close()
        for path in sorted(self.directory.iterdir()):
            path.unlink()
        self.directory.rmdir()

    def test_the_raw_frame_is_written_before_anything_is_enqueued(self):
        """A frame that decodes to nothing still leaves raw evidence."""
        self.harness.feed(_frame(200, logs=["Program log: unrelated"]))
        self.assertEqual(self.harness.raw.count, 1)
        self.assertEqual(self.harness.queue.qsize(), 0)
        self.assertEqual(self.harness.rows("observation"), [])

    def test_a_failed_transaction_is_recorded_and_not_scheduled(self):
        self.harness.feed(_create_frame(200).replace('"err": null', '"err": {"X": 1}'))
        self.assertEqual(self.harness.raw.count, 1)
        self.assertEqual(self.harness.queue.qsize(), 0)

    def test_a_create_produces_one_observation_and_three_targets(self):
        self.harness.feed(_create_frame(200))
        self.assertEqual(self.harness.counts["launches"], 1)
        observations = self.harness.rows("observation")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0][0], SIGNATURE)
        self.assertEqual(observations[0][8], B15I.FORK_UNCONFIRMED)
        targets = self.harness.connection.execute(
            "SELECT delay_slots, target_slot, lead_slots, state FROM target "
            "ORDER BY delay_slots").fetchall()
        self.assertEqual(targets, [(1, 201, 1, "pending"), (2, 202, 2, "pending"),
                                   (4, 204, 4, "pending")])
        self.assertEqual(self.harness.queue.qsize(), 3)

    def test_the_observation_exists_before_the_target_that_refers_to_it(self):
        """Order, proven by content: every target's signature is already an observation row."""
        self.harness.feed(_create_frame(200))
        observed = {row[0] for row in self.harness.rows("observation")}
        referenced = {row[0] for row in self.harness.rows("target")}
        self.assertEqual(referenced - observed, set())

    def test_receipt_to_schedule_latency_is_recorded_and_monotonic(self):
        self.harness.feed(_create_frame(200))
        for (elapsed,) in self.harness.connection.execute(
                "SELECT receipt_to_schedule_ns FROM target"):
            self.assertGreater(elapsed, 0)

    def test_a_pre_activation_launch_is_never_scheduled(self):
        self.harness.feed(_create_frame(100))          # exactly at activation: excluded
        self.assertEqual(self.harness.counts["pre_activation"], 1)
        self.assertEqual(self.harness.rows("target"), [])
        self.assertEqual(len(self.harness.rows("observation")), 1)   # evidence still kept

    def test_a_full_queue_records_the_drop_and_never_drops_silently(self):
        harness = Harness(self.directory / "full", max_depth=1)
        try:
            harness.feed(_create_frame(200))
            states = dict(harness.connection.execute(
                "SELECT delay_slots, state FROM target").fetchall())
            reasons = dict(harness.connection.execute(
                "SELECT delay_slots, reason FROM target").fetchall())
            self.assertEqual(harness.counts["overflow"], 2)
            self.assertEqual(states[2], B15I.STATE_REFUSED)
            self.assertEqual(reasons[4], B15I.Q_OVERFLOW)
            self.assertEqual(len(states), 3)          # all three visible, none absent
        finally:
            harness.raw.close()
            harness.connection.close()
            for path in sorted((self.directory / "full").iterdir()):
                path.unlink()
            (self.directory / "full").rmdir()

    def test_a_duplicate_frame_does_not_duplicate_the_observation(self):
        self.harness.feed(_create_frame(200))
        self.harness.feed(_create_frame(200))
        self.assertEqual(len(self.harness.rows("observation")), 1)
        self.assertEqual(len(self.harness.rows("target")), 3)
        self.assertEqual(self.harness.raw.count, 2)   # both frames kept

    def test_the_raw_log_survives_reopening(self):
        self.harness.feed(_create_frame(200))
        self.harness.raw.close()
        reopened = B15I.RawLog(self.directory / "raw.jsonl")
        self.assertEqual(reopened.count, 1)
        self.harness.raw = reopened


class TestCapture(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(f"b15i_cap_{self.id().split('.')[-1]}")
        self.directory.mkdir(exist_ok=True)
        self.harness = Harness(self.directory)
        self.harness.feed(_create_frame(200))
        self.record = self.harness.queue.get()
        self.checkpoint_document = B15F.verify_preregistration()
        self.curve_decoder = B15I.B15B.build_decoder()

    def tearDown(self):
        self.harness.raw.close()
        self.harness.connection.close()
        for path in sorted(self.directory.iterdir()):
            path.unlink()
        self.directory.rmdir()

    def _opener(self, response):
        class Handle:
            status = 200

            def read(self_inner):
                return json.dumps(response).encode()

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *_):
                return False
        return lambda request, timeout=None: Handle()

    def _account(self, context_slot, owner=PUMP_PROGRAM, data=None):
        raw = data if data is not None else _bonding_curve_bytes()
        return {"jsonrpc": "2.0", "id": 1,
                "result": {"context": {"slot": context_slot},
                           "value": {"owner": owner, "lamports": 5_000_000,
                                     "data": [base64.b64encode(raw).decode(), "base64"]}}}

    def _run(self, response):
        # No real sleeping: the retry interval is 25 slots, and a test that actually waits it out
        # takes fifty seconds to assert something that has nothing to do with timing.
        B15I.capture(self.record, "https://example.invalid", self.harness.connection,
                     self.harness.lock, self.curve_decoder, self.checkpoint_document,
                     self.harness.counts, self._opener(response), None, lambda _seconds: None)
        return self.harness.connection.execute(
            "SELECT state, reason, context_slot, lateness_slots, virtual_quote FROM target "
            "WHERE signature=? AND delay_slots=?",
            (self.record["signature"], self.record["delay_slots"])).fetchone()

    def test_a_clean_read_captures(self):
        state, reason, context_slot, lateness, virtual_quote = self._run(self._account(201))
        self.assertEqual((state, reason), (B15I.STATE_CAPTURED, None))
        self.assertEqual((context_slot, lateness), (201, 0))
        self.assertEqual(virtual_quote, 30_000_000_000)
        self.assertEqual(self.harness.counts["captured"], 1)

    def test_a_late_context_is_refused_not_recorded_as_the_state(self):
        state, reason, _slot, _late, virtual_quote = self._run(self._account(201 + 151))
        self.assertEqual(state, B15I.STATE_REFUSED)
        self.assertTrue(reason.startswith(B15I.Q_LATE))
        self.assertIsNone(virtual_quote)

    def test_lateness_exactly_at_the_tolerance_is_admitted(self):
        state, _reason, _slot, lateness, _quote = self._run(self._account(201 + 150))
        self.assertEqual((state, lateness), (B15I.STATE_CAPTURED, 150))

    def test_a_wrong_owner_is_an_account_mismatch(self):
        state, reason, *_ = self._run(self._account(201, owner="SomeOtherProgram11111111111"))
        self.assertEqual(state, B15I.STATE_REFUSED)
        self.assertTrue(reason.startswith(B15I.Q_ACCOUNT_MISMATCH))

    def test_a_wrong_discriminator_is_an_account_mismatch(self):
        poisoned = bytes([B15F.BONDING_CURVE_DISCRIMINATOR[0] ^ 0xFF]) + \
            B15F.BONDING_CURVE_DISCRIMINATOR[1:]
        state, reason, *_ = self._run(
            self._account(201, data=_bonding_curve_bytes(discriminator=poisoned)))
        self.assertEqual(state, B15I.STATE_REFUSED)
        self.assertTrue(reason.startswith(B15I.Q_ACCOUNT_MISMATCH))

    def test_an_rpc_failure_is_refused_with_its_own_code(self):
        state, reason, *_ = self._run({"jsonrpc": "2.0", "id": 1,
                                       "error": {"code": -32016, "message": "min context slot"}})
        self.assertEqual(state, B15I.STATE_REFUSED)
        self.assertTrue(reason.startswith(B15I.Q_RPC_FAILED))

    def test_the_request_carries_min_context_slot_at_the_target(self):
        """The node waits for the target; the client never polls for it."""
        seen = {}

        def opener(request, timeout=None):
            seen.update(json.loads(request.data))

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(self._account(201)).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        B15I.capture(self.record, "https://example.invalid", self.harness.connection,
                     self.harness.lock, self.curve_decoder, self.checkpoint_document,
                     self.harness.counts, opener)
        options = seen["params"][1]
        self.assertEqual(options["minContextSlot"], self.record["target_slot"])
        self.assertEqual(options["commitment"], B15I.STATE_READ_COMMITMENT)
        self.assertEqual(options["commitment"], "finalized")

    def test_a_context_not_reached_error_is_retried_a_bounded_number_of_times(self):
        """minContextSlot does NOT make the node wait. It rejects, and B15F's bounded retry runs.

        147 of 147 live requests came back `-32603 Min context slot not reached` in about 220ms.
        The parameter is a precondition the node checks, not a barrier it blocks on.
        """
        calls, slept = [], []
        not_reached = {"jsonrpc": "2.0", "id": 1,
                       "code": -32603, "message": "Min context slot not reached"}

        def opener(request, timeout=None):
            calls.append(1)

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(not_reached).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        B15I.capture(self.record, "https://example.invalid", self.harness.connection,
                     self.harness.lock, self.curve_decoder, self.checkpoint_document,
                     self.harness.counts, opener, None, slept.append)
        attempts = self.checkpoint_document["context_slot_geometry"]["max_attempts"]
        self.assertEqual(len(calls), attempts)          # bounded, not unbounded
        self.assertEqual(len(slept), attempts - 1)      # no sleep after the last attempt
        interval = self.checkpoint_document["context_slot_geometry"]["retry_interval_slots"]
        self.assertEqual(set(slept), {interval * B15I.SLOT_SECONDS})
        state, reason, recorded = self.harness.connection.execute(
            "SELECT state, reason, attempts FROM target WHERE signature=? AND delay_slots=?",
            (self.record["signature"], self.record["delay_slots"])).fetchone()
        self.assertEqual((state, recorded), (B15I.STATE_REFUSED, attempts))
        self.assertIn(f"after {attempts} attempts", reason)

    def test_a_target_reached_on_a_later_attempt_is_captured(self):
        responses = [{"jsonrpc": "2.0", "id": 1, "code": -32603,
                      "message": "Min context slot not reached"},
                     {"jsonrpc": "2.0", "id": 1, "code": -32603,
                      "message": "Min context slot not reached"},
                     self._account(210)]

        def opener(request, timeout=None):
            payload = responses.pop(0)

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(payload).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        B15I.capture(self.record, "https://example.invalid", self.harness.connection,
                     self.harness.lock, self.curve_decoder, self.checkpoint_document,
                     self.harness.counts, opener, None, lambda _seconds: None)
        state, attempts, lateness = self.harness.connection.execute(
            "SELECT state, attempts, lateness_slots FROM target WHERE signature=? AND "
            "delay_slots=?", (self.record["signature"], self.record["delay_slots"])).fetchone()
        self.assertEqual((state, attempts), (B15I.STATE_CAPTURED, 3))
        self.assertEqual(lateness, 210 - self.record["target_slot"])

    def test_retrying_never_admits_a_response_past_the_tolerance(self):
        """The retry budget must not become a way in for a stale answer."""
        responses = [{"jsonrpc": "2.0", "id": 1, "code": -32603,
                      "message": "Min context slot not reached"},
                     self._account(self.record["target_slot"] + 151)]

        def opener(request, timeout=None):
            payload = responses.pop(0)

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(payload).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        B15I.capture(self.record, "https://example.invalid", self.harness.connection,
                     self.harness.lock, self.curve_decoder, self.checkpoint_document,
                     self.harness.counts, opener, None, lambda _seconds: None)
        state, reason = self.harness.connection.execute(
            "SELECT state, reason FROM target WHERE signature=? AND delay_slots=?",
            (self.record["signature"], self.record["delay_slots"])).fetchone()
        self.assertEqual(state, B15I.STATE_REFUSED)
        self.assertTrue(reason.startswith(B15I.Q_LATE))

    def test_an_error_that_is_not_context_not_reached_is_never_retried(self):
        calls = []

        def opener(request, timeout=None):
            calls.append(1)

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps({"jsonrpc": "2.0", "id": 1,
                                       "error": {"code": -32602,
                                                 "message": "Invalid param"}}).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        B15I.capture(self.record, "https://example.invalid", self.harness.connection,
                     self.harness.lock, self.curve_decoder, self.checkpoint_document,
                     self.harness.counts, opener, None, lambda _seconds: None)
        self.assertEqual(len(calls), 1)

    def test_the_context_not_reached_detector_does_not_match_unrelated_errors(self):
        self.assertTrue(B15I._context_not_reached(
            {"code": -32603, "message": "Min context slot not reached"}))
        self.assertFalse(B15I._context_not_reached({"code": -32602, "message": "Invalid param"}))
        self.assertFalse(B15I._context_not_reached("transport_error"))

    def test_queue_delay_is_recorded(self):
        self._run(self._account(201))
        (delay,) = self.harness.connection.execute(
            "SELECT queue_delay_ns FROM target WHERE signature=? AND delay_slots=?",
            (self.record["signature"], self.record["delay_slots"])).fetchone()
        self.assertGreaterEqual(delay, 0)



class TestRecovery(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(f"b15i_rec_{self.id().split('.')[-1]}")
        self.directory.mkdir(exist_ok=True)
        self.harness = Harness(self.directory)
        self.harness.feed(_create_frame(200))

    def tearDown(self):
        self.harness.raw.close()
        self.harness.connection.close()
        for path in sorted(self.directory.iterdir()):
            path.unlink()
        self.directory.rmdir()

    def test_a_target_missed_while_down_is_refused_and_never_fetched(self):
        recovered = B15I.recover_pending(self.harness.connection, self.harness.lock, 100_000)
        self.assertEqual(recovered, 3)
        states = self.harness.connection.execute(
            "SELECT DISTINCT state, reason FROM target").fetchall()
        self.assertEqual(states, [(B15I.STATE_REFUSED, B15I.Q_MISSED_WHILE_DOWN)])
        # No state was written for any of them: nothing was fetched to stand in.
        self.assertEqual(self.harness.connection.execute(
            "SELECT COUNT(*) FROM target WHERE virtual_quote IS NOT NULL").fetchone()[0], 0)

    def test_a_target_still_inside_the_tolerance_stays_pending(self):
        recovered = B15I.recover_pending(self.harness.connection, self.harness.lock, 300)
        self.assertEqual(recovered, 0)
        self.assertEqual(self.harness.connection.execute(
            "SELECT COUNT(*) FROM target WHERE state='pending'").fetchone()[0], 3)


class TestReconciliation(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(f"b15i_fork_{self.id().split('.')[-1]}")
        self.directory.mkdir(exist_ok=True)
        self.harness = Harness(self.directory)

    def tearDown(self):
        self.harness.raw.close()
        self.harness.connection.close()
        for path in sorted(self.directory.iterdir()):
            path.unlink()
        self.directory.rmdir()

    def _b15a(self, signatures, tip=100_000):
        """A confirmed recorder holding `signatures` and having itself progressed to `tip`.

        The tip is the point. Without it, a recorder that has not reached a slot yet and one that
        reached it and saw nothing are indistinguishable, and they mean opposite things.
        """
        import sqlite3
        path = self.directory / "shadow.sqlite"
        connection = sqlite3.connect(path)
        # Rebuilt, not appended to: this helper is called twice in one test, and a version that
        # accumulated would make the second call's assertion depend on the first call's rows.
        connection.execute(
            "CREATE TABLE IF NOT EXISTS launch(signature TEXT, decode_status TEXT, slot INTEGER)")
        connection.execute("CREATE TABLE IF NOT EXISTS pump_event(slot INTEGER)")
        connection.execute("DELETE FROM launch")
        connection.execute("DELETE FROM pump_event")
        connection.executemany("INSERT INTO launch VALUES (?,'decoded',?)",
                               [(s, tip) for s in signatures])
        connection.execute("INSERT INTO pump_event VALUES (?)", (tip,))
        connection.commit()
        connection.close()
        return path

    def test_a_corroborated_observation_is_promoted(self):
        self.harness.feed(_create_frame(200))
        counts = B15I.reconcile(self.harness.connection, self.harness.lock,
                                self._b15a([SIGNATURE]), self.directory / "missing.sqlite")
        self.assertEqual(counts[B15I.FORK_CONFIRMED], 1)
        self.assertEqual(self.harness.connection.execute(
            "SELECT fork_state FROM observation").fetchone()[0], B15I.FORK_CONFIRMED)

    def test_an_uncorroborated_observation_the_recorder_passed_is_orphaned(self):
        self.harness.feed(_create_frame(200))
        self.harness.feed(_create_frame(1000, signature="Other" + SIGNATURE[5:]))
        counts = B15I.reconcile(self.harness.connection, self.harness.lock,
                                self._b15a([], tip=1000 + B15I.ORPHAN_MARGIN_SLOTS + 1),
                                self.directory / "missing.sqlite")
        self.assertEqual(counts[B15I.FORK_ORPHANED], 2)
        self.assertEqual(counts[B15I.FORK_CONFIRMED], 0)

    def test_a_lagging_recorder_never_orphans_what_it_has_not_reached(self):
        """B15a was found running 500 slots behind. Its silence there means nothing yet.

        The rule keyed on our own newest observation called 112 launches orphaned that the
        counterparty simply had not got to — laundering counterparty lag into a finding.
        """
        self.harness.feed(_create_frame(200))
        self.harness.feed(_create_frame(5000, signature="Other" + SIGNATURE[5:]))
        counts = B15I.reconcile(self.harness.connection, self.harness.lock,
                                self._b15a([], tip=400),   # behind both, past neither by the margin
                                self.directory / "missing.sqlite")
        self.assertEqual(counts[B15I.FORK_ORPHANED], 0)
        self.assertEqual(counts[B15I.FORK_UNRESOLVED], 2)

    def test_the_furthest_behind_counterparty_sets_the_bar(self):
        """A current recorder must not excuse orphaning what the other one has not reached."""
        import sqlite3
        self.harness.feed(_create_frame(200))
        behind = self.directory / "backfill.sqlite"
        connection = sqlite3.connect(behind)
        connection.execute("CREATE TABLE backfill(signature TEXT, status TEXT, slot INTEGER)")
        connection.execute("INSERT INTO backfill VALUES ('x','retrieved',150)")
        connection.commit()
        connection.close()
        _confirmed, tip = B15I.counterparty_evidence(self._b15a([], tip=100_000), behind)
        self.assertEqual(tip, 150)
        counts = B15I.reconcile(self.harness.connection, self.harness.lock,
                                self._b15a([], tip=100_000), behind)
        self.assertEqual(counts[B15I.FORK_ORPHANED], 0)

    def test_a_recent_observation_is_unresolved_not_orphaned(self):
        self.harness.feed(_create_frame(200))
        counts = B15I.reconcile(self.harness.connection, self.harness.lock,
                                self._b15a([], tip=250), self.directory / "missing.sqlite")
        self.assertEqual(counts[B15I.FORK_UNRESOLVED], 1)

    def test_a_missing_counterparty_database_never_promotes_and_never_orphans(self):
        self.harness.feed(_create_frame(200))
        counts = B15I.reconcile(self.harness.connection, self.harness.lock,
                                self.directory / "absent_a.sqlite",
                                self.directory / "absent_b.sqlite")
        self.assertEqual(counts[B15I.FORK_CONFIRMED], 0)
        # Unknown is not clean, and it is not dirty either: with no counterparty readable at all,
        # nothing is orphaned on the strength of an absence nobody could check.
        self.assertEqual(counts[B15I.FORK_ORPHANED], 0)
        self.assertEqual(counts[B15I.FORK_UNRESOLVED], 1)
        self.assertIsNone(B15I.counterparty_evidence(
            self.directory / "absent_a.sqlite", self.directory / "absent_b.sqlite")[1])

    def test_only_confirmed_cells_are_counted_priceable(self):
        self.harness.feed(_create_frame(200))
        self.harness.connection.execute(
            "UPDATE target SET state='captured', virtual_quote=1 WHERE delay_slots=1")
        self.harness.connection.commit()
        B15I.reconcile(self.harness.connection, self.harness.lock,
                       self._b15a([]), self.directory / "missing.sqlite")
        report = B15I.census(self.harness.connection)
        self.assertEqual(report["priceable_cells"], 0)
        self.assertEqual(report["captured_but_not_priceable"], 1)
        B15I.reconcile(self.harness.connection, self.harness.lock,
                       self._b15a([SIGNATURE]), self.directory / "missing.sqlite")
        report = B15I.census(self.harness.connection)
        self.assertEqual(report["priceable_cells"], 1)


class TestCensus(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(f"b15i_cen_{self.id().split('.')[-1]}")
        self.directory.mkdir(exist_ok=True)
        self.harness = Harness(self.directory)

    def tearDown(self):
        self.harness.raw.close()
        self.harness.connection.close()
        for path in sorted(self.directory.iterdir()):
            path.unlink()
        self.directory.rmdir()

    def test_reachability_is_reported_per_delay(self):
        self.harness.feed(_create_frame(200))
        report = B15I.census(self.harness.connection)
        self.assertEqual(sorted(report["lead_slots_by_delay"]), ["1", "2", "4"])
        for delay, entry in report["lead_slots_by_delay"].items():
            self.assertTrue(entry["reachable"])
            self.assertEqual(entry["min"], int(delay))

    def test_an_unreachable_delay_reports_unreachable_rather_than_being_absent(self):
        """Late arrival: the frame reaches us three slots after t0, so t0+1 and t0+2 are gone."""
        self.harness.connection.execute(
            "INSERT INTO target(signature,delay_slots,bonding_curve,target_slot,lead_slots,"
            "enqueued_wall_unix,enqueued_monotonic_ns,receipt_to_schedule_ns,state,reason,"
            "evidence_sha256) VALUES ('S',1,'C',201,-2,1.0,1,1,'refused',?,'x')",
            (B15I.Q_TARGET_ALREADY_PASSED,))
        self.harness.connection.commit()
        report = B15I.census(self.harness.connection)
        entry = report["lead_slots_by_delay"]["1"]
        self.assertFalse(entry["reachable"])
        self.assertEqual(entry["still_future_at_scheduling"], 0)
        self.assertEqual(report["refusals"][B15I.Q_TARGET_ALREADY_PASSED], 1)

    def test_the_census_publishes_no_return_and_carries_the_status_locks(self):
        report = B15I.census(self.harness.connection)
        text = json.dumps(report).lower()
        for banned in ("profit", "pnl", "return_pct", "roi", "landing_probability"):
            self.assertNotIn(banned, text)
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertEqual(report["label"], B15I.LABEL)
        self.assertIn("missed-launch incidence is not estimable", report["coverage_statement"])

    def test_the_census_states_both_commitments(self):
        report = B15I.census(self.harness.connection)
        self.assertEqual(report["trigger_commitment"], "processed")
        self.assertEqual(report["state_read_commitment"], "finalized")


class TestWorkerLoop(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(f"b15i_wl_{self.id().split('.')[-1]}")
        self.directory.mkdir(exist_ok=True)
        self.harness = Harness(self.directory)
        self.harness.feed(_create_frame(200))

    def tearDown(self):
        self.harness.raw.close()
        self.harness.connection.close()
        for path in sorted(self.directory.iterdir()):
            path.unlink()
        self.directory.rmdir()

    def test_a_throwing_worker_records_the_failure_and_keeps_draining(self):
        stop = threading.Event()

        def exploding(request, timeout=None):
            raise MemoryError("the drain must not die with it")

        thread = threading.Thread(
            target=B15I.worker_loop,
            args=(self.harness.queue, "https://example.invalid", self.harness.connection,
                  self.harness.lock, B15I.B15B.build_decoder(), B15F.verify_preregistration(),
                  self.harness.counts, stop, exploding, None), daemon=True)
        thread.start()
        self.harness.queue.join()
        stop.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        states = self.harness.connection.execute(
            "SELECT COUNT(*) FROM target WHERE state='refused'").fetchone()[0]
        self.assertEqual(states, 3)          # all three drained, none left pending
        self.assertEqual(self.harness.connection.execute(
            "SELECT COUNT(*) FROM target WHERE state='pending'").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
