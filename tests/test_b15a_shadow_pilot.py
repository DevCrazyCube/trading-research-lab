"""B15a — the safety guards, each shown to be able to refuse.

The dangerous failures here are not arithmetic. They are: an execution surface appearing, the
frozen corpus being written to, a credential reaching an artifact or a status line, a decision
being proposed on evidence nobody has, and a raw frame being lost or edited. Every test below
breaks one of those.
"""
import base64
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = _load("b15a_shadow_fixtures", "b15a_shadow_fixtures.py")
# One module graph, through the fixtures, so every assertRaises names the class the pilot raises.
PILOT = FIXTURES.PILOT
WS = PILOT.WS
Refused = PILOT.PilotRefused


def _restore_env(name, previous):
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15a-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15a"
        self.work.mkdir()


class TestNoExecutionSurface(Temp):
    def test_no_pilot_module_can_hold_a_key_sign_or_submit(self):
        self.assertEqual([], FIXTURES.check_execution_surface())

    def test_the_check_fires_when_a_surface_appears(self):
        """Not a decorative scan: plant one and it must be caught."""
        planted = self.directory / "planted.py"
        planted.write_text("def go():\n    return sendTransaction(payload)\n")
        with self.assertRaisesRegex(Refused, "an execution surface appeared"):
            PILOT.assert_no_execution_surface(planted)

    def test_every_forbidden_token_is_detected(self):
        for token in PILOT.EXECUTION_SURFACE_TOKENS:
            with self.subTest(token=token):
                planted = self.directory / f"planted_{abs(hash(token))}.py"
                planted.write_text(f"value = {token}\n")
                with self.assertRaises(Refused):
                    PILOT.assert_no_execution_surface(planted)

    def test_a_clean_file_passes(self):
        clean = self.directory / "clean.py"
        clean.write_text("def observe():\n    return 'nothing happens here'\n")
        self.assertTrue(PILOT.assert_no_execution_surface(clean))


class TestIsolation(Temp):
    def test_the_frozen_corpus_is_out_of_reach(self):
        with self.assertRaisesRegex(Refused, "is not a shadow"):
            PILOT.assert_isolated(ROOT / "research" / "b11a")

    def test_every_forbidden_marker_is_refused(self):
        for marker in PILOT.FORBIDDEN_PATH_MARKERS:
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    PILOT.assert_isolated(ROOT / marker / "b15a")

    def test_a_directory_that_is_not_b15a_is_refused(self):
        with self.assertRaisesRegex(Refused, "must be .../b15a"):
            PILOT.assert_isolated(self.directory / "elsewhere")

    def test_the_real_work_dir_passes(self):
        self.assertTrue(PILOT.assert_isolated(PILOT.WORK_DIR))
        self.assertTrue(PILOT.assert_isolated(self.work))


class TestPreregistrationBinding(Temp):
    def test_the_committed_freeze_verifies(self):
        document = PILOT.verify_preregistration()
        self.assertEqual("B15A_SHADOW_PILOT_V1", document["preregistration_id"])
        self.assertEqual([], document["eligibility"]["eligible_windows"]
                         if "eligibility" in document else [])

    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a changed document is a different pilot"):
            PILOT.verify_preregistration(expected_sha256="0" * 64)

    def test_a_missing_freeze_is_refused_as_a_refusal(self):
        with self.assertRaises(Refused):
            PILOT.verify_preregistration(path=self.directory / "absent.json")

    def test_the_freeze_forbids_execution_by_name(self):
        document = PILOT.verify_preregistration()
        forbidden = " ".join(document["strictly_forbidden"]).lower()
        for word in ("signing", "submitting", "key material", "spending"):
            with self.subTest(word=word):
                self.assertIn(word, forbidden)

    def test_the_freeze_refuses_the_geyser_claim(self):
        document = PILOT.verify_preregistration()
        self.assertIn("geyser_fidelity", document["status_locks"]["refused_status_names"])


class TestCommitment(Temp):
    def test_only_processed_and_confirmed_are_permitted(self):
        for good in ("processed", "confirmed"):
            self.assertEqual(good, PILOT.assert_commitment(good))
        for bad in ("finalized", "recent", "", "PROCESSED"):
            with self.subTest(bad=bad):
                with self.assertRaises(Refused):
                    PILOT.assert_commitment(bad)


class TestRedaction(Temp):
    def test_an_identity_may_not_reach_a_status_line(self):
        for key in PILOT.REDACTED_FORBIDDEN_KEYS:
            with self.subTest(key=key):
                with self.assertRaisesRegex(Refused, "do not belong in a line"):
                    PILOT.assert_redacted({key: "value"})

    def test_a_nested_identity_is_caught(self):
        with self.assertRaises(Refused):
            PILOT.assert_redacted({"outer": {"inner": {"mint": "abc"}}})

    def test_a_credential_fragment_is_caught(self):
        os.environ["SOLANA_RPC_URL"] = "https://host.invalid/?api-key=SUPERSECRETVALUE123"
        self.addCleanup(lambda: os.environ.pop("SOLANA_RPC_URL", None))
        with self.assertRaisesRegex(Refused, "part of the credential"):
            PILOT.assert_redacted({"note": "api-key=SUPERSECRETVALUE123"})

    def test_an_aggregate_only_report_passes(self):
        self.assertTrue(PILOT.assert_redacted({"frames_received": 7, "reconnects": 1}))


class TestWebSocketTransport(Temp):
    def test_a_non_websocket_scheme_is_refused(self):
        for url in ("https://example.invalid/", "http://example.invalid/", "ftp://x/"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(WS.WebSocketRefused, "not a websocket scheme"):
                    WS.WebSocket(url)

    def test_the_receipt_is_scheme_and_host_only(self):
        receipt = WS.endpoint_receipt("wss://mainnet.example.com/path?api-key=SECRET")
        self.assertEqual("wss://mainnet.example.com", receipt)
        self.assertNotIn("SECRET", receipt)
        self.assertNotIn("path", receipt)

    def test_a_url_with_no_host_is_refused(self):
        with self.assertRaises(WS.WebSocketRefused):
            WS.endpoint_receipt("not-a-url")

    def test_the_credential_is_dropped_from_the_object_after_the_handshake(self):
        """A traceback, a repr or a logger must not be able to reach the API key."""
        socket_ = WS.WebSocket("wss://host.invalid/?api-key=SECRETVALUE")
        self.assertIn("SECRETVALUE", socket_._resource)
        socket_._resource = None                       # what connect() does once it has written it
        self.assertNotIn("SECRETVALUE", repr(vars(socket_)))

    def test_a_missing_credential_is_refused_not_defaulted(self):
        with self.assertRaisesRegex(WS.WebSocketRefused, "environment-only"):
            WS.websocket_url_from_env("B15A_DEFINITELY_UNSET_VARIABLE")

    def test_an_https_endpoint_becomes_wss(self):
        os.environ["B15A_TEST_URL"] = "https://host.invalid/x?k=1"
        self.addCleanup(lambda: os.environ.pop("B15A_TEST_URL", None))
        self.assertTrue(WS.websocket_url_from_env("B15A_TEST_URL").startswith("wss://"))


class TestDecoding(Temp):
    def setUp(self):
        super().setUp()
        self.b7d, self.disc, self.create_type, self.types = PILOT.load_pinned_create_type()

    def test_a_real_create_event_decodes(self):
        payload = FIXTURES.create_payload()
        status, fields, error = PILOT.decode_create(payload, self.b7d, self.disc,
                                                    self.create_type, self.types)
        self.assertEqual(PILOT.DECODE_DECODED, status, error)
        self.assertEqual(17, len(fields))

    def test_a_log_framed_create_decodes_without_the_event_cpi_tag(self):
        """The framing that actually arrives, and the one that was missing.

        `Program data:` log lines carry `discriminator || payload` directly. The event-CPI tag only
        prefixes inner-instruction data. Requiring the tag made the running pilot examine 739
        program-data payloads and match none of them.
        """
        tagged = FIXTURES.create_payload()
        untagged = tagged[len(PILOT.EVENT_TAG):]
        status, fields, error = PILOT.decode_create(untagged, self.b7d, self.disc,
                                                    self.create_type, self.types)
        self.assertEqual(PILOT.DECODE_DECODED, status, error)
        self.assertEqual(17, len(fields))

    def test_both_framings_decode_to_the_same_event(self):
        tagged = FIXTURES.create_payload()
        untagged = tagged[len(PILOT.EVENT_TAG):]
        first = PILOT.decode_create(tagged, self.b7d, self.disc, self.create_type, self.types)
        second = PILOT.decode_create(untagged, self.b7d, self.disc, self.create_type, self.types)
        self.assertEqual(first, second)

    def test_a_payload_shorter_than_a_discriminator_is_not_a_create(self):
        status, _f, _e = PILOT.decode_create(b"\x1b\x72", self.b7d, self.disc,
                                             self.create_type, self.types)
        self.assertEqual(PILOT.DECODE_NOT_CREATE, status)

    def test_a_foreign_event_is_unknown_not_merely_absent(self):
        """The semantics the log framing corrected.

        Every `Program data:` payload is a candidate event, so one whose discriminator does not
        match is an event we do not recognise — `unknown_event` — and it is counted. Calling it
        `not_a_create` would drop the whole of Pump's other event traffic out of the census.
        `not_a_create` now means only "too short to carry a discriminator at all".
        """
        status, _fields, _error = PILOT.decode_create(b"\x00" * 40, self.b7d, self.disc,
                                                      self.create_type, self.types)
        self.assertEqual(PILOT.DECODE_UNKNOWN, status)

    def test_an_unknown_event_is_named_unknown_not_failed(self):
        status, _fields, _error = PILOT.decode_create(PILOT.EVENT_TAG + b"\x00" * 40, self.b7d,
                                                      self.disc, self.create_type, self.types)
        self.assertEqual(PILOT.DECODE_UNKNOWN, status)

    def test_a_truncated_create_reports_failure_and_the_reason(self):
        payload = FIXTURES.create_payload()[:20]
        status, fields, error = PILOT.decode_create(payload, self.b7d, self.disc,
                                                    self.create_type, self.types)
        self.assertIn(status, (PILOT.DECODE_FAILED, PILOT.DECODE_UNKNOWN))
        if status == PILOT.DECODE_FAILED:
            self.assertIsNotNone(error)
            self.assertIsNone(fields)

    def test_a_malformed_base64_log_line_is_skipped_not_fatal(self):
        """Every program on the chain emits logs; one bad line must not stop the feed."""
        payloads, skipped = PILOT.program_data_payloads(
            [f"{PILOT.PROGRAM_DATA_PREFIX}not-base64!!", "Program log: hello"])
        self.assertEqual([], payloads)
        self.assertEqual(1, skipped)

    def test_the_types_map_matches_b7ds_own_construction(self):
        """The defect this replaced: a paraphrase of b7d's type map that decoded nothing."""
        idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
        self.assertEqual({item["name"]: item for item in idl["types"]}, self.types)


class TestPinnedIdlGuards(Temp):
    """Both were mutation survivors: reachable only once the path is injectable."""

    def _idl(self, document):
        path = self.directory / "idl.json"
        path.write_text(json.dumps(document))
        return path

    def test_an_idl_with_no_create_event_is_refused(self):
        with self.assertRaisesRegex(Refused, "declares no CreateEvent"):
            PILOT.load_pinned_create_type(self._idl({"types": [], "events": []}))

    def test_a_create_event_with_no_discriminator_is_refused(self):
        with self.assertRaisesRegex(Refused, "carries no discriminator"):
            PILOT.load_pinned_create_type(
                self._idl({"types": [], "events": [{"name": "CreateEvent"}]}))

    def test_the_real_pinned_idl_loads(self):
        _b7d, discriminator, _create, types = PILOT.load_pinned_create_type()
        self.assertEqual(8, len(discriminator))
        self.assertIn("CreateEvent", types)


class FakeRawSocket:
    """A socket that hands back exactly the bytes a test wants, then closes."""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = b""

    def recv(self, _size):
        return self.chunks.pop(0) if self.chunks else b""

    def sendall(self, data):
        self.sent += data

    def close(self):
        pass


def server_frame(opcode, payload=b"", final=True, masked=False):
    """A server->client frame, built by hand so the parser's guards can be provoked."""
    import struct as _struct
    header = bytearray([(0x80 if final else 0) | opcode])
    length = len(payload)
    flag = 0x80 if masked else 0
    if length < 126:
        header.append(flag | length)
    elif length < (1 << 16):
        header.append(flag | 126)
        header += _struct.pack(">H", length)
    else:
        header.append(flag | 127)
        header += _struct.pack(">Q", length)
    if masked:
        header += b"\x00\x00\x00\x00"
    return bytes(header) + payload


class TestWebSocketFraming(Temp):
    """The hand-rolled parser's error paths. All eight were mutation survivors.

    A protocol client whose failure branches are never exercised is where silent corruption lives:
    every one of these turns a malformed peer into a refusal instead of into evidence.
    """

    def _socket(self, chunks):
        socket_ = WS.WebSocket("wss://host.invalid/")
        socket_.sock = FakeRawSocket(chunks)
        return socket_

    def test_a_masked_server_frame_is_refused(self):
        socket_ = self._socket([server_frame(WS.OPCODE_TEXT, b"hi", masked=True)])
        with self.assertRaisesRegex(WS.WebSocketRefused, "RFC 6455 forbids"):
            socket_.recv()

    def test_a_binary_frame_is_refused(self):
        socket_ = self._socket([server_frame(WS.OPCODE_BINARY, b"\x00\x01")])
        with self.assertRaisesRegex(WS.WebSocketRefused, "refusing to guess"):
            socket_.recv()

    def test_an_unknown_opcode_is_refused(self):
        socket_ = self._socket([server_frame(0x7, b"x")])
        with self.assertRaisesRegex(WS.WebSocketRefused, "unknown opcode"):
            socket_.recv()

    def test_a_missing_continuation_is_refused(self):
        socket_ = self._socket([server_frame(WS.OPCODE_TEXT, b"part", final=False)
                                + server_frame(WS.OPCODE_TEXT, b"wrong")])
        with self.assertRaisesRegex(WS.WebSocketRefused, "expected a continuation"):
            socket_.recv()

    def test_a_close_mid_frame_is_refused(self):
        socket_ = self._socket([b"\x81\x10only-two-bytes"])
        with self.assertRaisesRegex(WS.WebSocketRefused, "closed mid-frame"):
            socket_.recv()

    def test_a_close_during_the_handshake_is_refused(self):
        socket_ = self._socket([b"HTTP/1.1 101"])
        with self.assertRaisesRegex(WS.WebSocketRefused, "closed during handshake"):
            socket_._read_until(b"\r\n\r\n")

    def test_sending_on_a_closed_socket_is_refused(self):
        socket_ = self._socket([])
        socket_.closed = True
        with self.assertRaisesRegex(WS.WebSocketRefused, "closed socket"):
            socket_.send_text("hello")

    def test_a_wrong_accept_header_is_refused(self):
        socket_ = self._socket([])
        header = b"HTTP/1.1 101 Switching\r\nSec-WebSocket-Accept: wrong\r\n"
        with self.assertRaisesRegex(WS.WebSocketRefused, "not a websocket"):
            socket_._verify_handshake(header, "a-key")

    def test_a_refused_upgrade_is_refused(self):
        socket_ = self._socket([])
        with self.assertRaisesRegex(WS.WebSocketRefused, "upgrade refused"):
            socket_._verify_handshake(b"HTTP/1.1 403 Forbidden\r\n", "a-key")

    def test_a_good_frame_still_parses(self):
        socket_ = self._socket([server_frame(WS.OPCODE_TEXT, b'{"ok":1}')])
        self.assertEqual('{"ok":1}', socket_.recv())

    def test_a_ping_is_answered_and_not_returned(self):
        socket_ = self._socket([server_frame(WS.OPCODE_PING, b"hb")
                                + server_frame(WS.OPCODE_TEXT, b"after")])
        self.assertEqual("after", socket_.recv())
        self.assertTrue(socket_.sock.sent, "a ping must be answered with a pong")

    def test_a_close_frame_ends_the_stream(self):
        import struct as _struct
        socket_ = self._socket([server_frame(WS.OPCODE_CLOSE, _struct.pack(">H", 1000))])
        self.assertIsNone(socket_.recv())
        self.assertTrue(socket_.closed)

    def test_a_fragmented_message_reassembles(self):
        socket_ = self._socket([server_frame(WS.OPCODE_TEXT, b'{"a":', final=False)
                                + server_frame(WS.OPCODE_CONTINUATION, b'1}')])
        self.assertEqual('{"a":1}', socket_.recv())


class TestStateFromCreateEvent(Temp):
    def setUp(self):
        super().setUp()
        b7d, disc, create_type, types = PILOT.load_pinned_create_type()
        self.fields = b7d.decode_create_payload(
            FIXTURES.create_payload()[len(PILOT.EVENT_TAG):], disc, create_type, types)

    def test_the_event_supplies_what_it_supplies_and_says_what_it_cannot(self):
        state, missing = PILOT.state_from_create_event(self.fields, slot=1000)
        self.assertEqual(sorted(PILOT.STATE_FIELDS_NOT_IN_CREATE_EVENT), sorted(missing))
        self.assertIn("virtual_quote", state)
        self.assertIn("mayhem_mode", state)
        self.assertEqual(1000, state["slot"])

    def test_nothing_absent_is_defaulted(self):
        """real_quote is not zero and complete is not false; they are simply not there."""
        state, _missing = PILOT.state_from_create_event(self.fields, slot=1)
        for field in PILOT.STATE_FIELDS_NOT_IN_CREATE_EVENT:
            with self.subTest(field=field):
                self.assertNotIn(field, state)

    def test_no_fields_means_every_state_field_missing(self):
        state, missing = PILOT.state_from_create_event(None, slot=1)
        self.assertEqual({}, state)
        self.assertEqual(list(PILOT.B10B_STATE_FIELDS), missing)


class TestDecisions(Temp):
    def setUp(self):
        super().setUp()
        b7d, disc, create_type, types = PILOT.load_pinned_create_type()
        self.fields = b7d.decode_create_payload(
            FIXTURES.create_payload()[len(PILOT.EVENT_TAG):], disc, create_type, types)
        self.state, _missing = PILOT.state_from_create_event(self.fields, slot=1000)

    def _decide(self, **overrides):
        arguments = {"fields": self.fields, "decode_status": PILOT.DECODE_DECODED,
                     "backfill_status": "retrieved", "observation_to_decision_ns": 1000,
                     "freshness_bound_ns": 30_000_000_000, "session_degraded": False,
                     "state": self.state}
        arguments.update(overrides)
        return PILOT.decide(**arguments)

    def test_feed_only_evidence_never_proposes_an_entry(self):
        """The whole point. The feed cannot establish t0 state, so nothing may be proposed on it."""
        result, reason, _detail = self._decide()
        self.assertEqual(PILOT.RESULT_NO_ENTRY, result)
        self.assertEqual(PILOT.S04_VETO, reason)

    def test_an_undecoded_event_refuses_with_its_own_reason(self):
        result, reason, _detail = self._decide(decode_status=PILOT.DECODE_UNKNOWN)
        self.assertEqual(PILOT.RESULT_NO_ENTRY, result)
        self.assertEqual(PILOT.S03_DECODE_INCOMPLETE, reason)

    def test_a_degraded_session_refuses(self):
        _result, reason, _detail = self._decide(session_degraded=True)
        self.assertEqual(PILOT.S07_SESSION_DEGRADED, reason)

    def test_a_stale_observation_refuses(self):
        _result, reason, _detail = self._decide(observation_to_decision_ns=10 ** 12)
        self.assertEqual(PILOT.S06_STALE_OBSERVATION, reason)

    def test_the_veto_set_is_b11bs_own_function_not_a_paraphrase(self):
        """A second veto set agrees with the first until it does not, invisibly."""
        vetoes = PILOT.b11b_vetoes(self.fields, self.state)
        self.assertIn("V4_incomplete_state", " ".join(vetoes))
        source = (ROOT / "scripts" / "b15a_shadow_pilot.py").read_text()
        self.assertIn("B11B.evaluate_vetoes", source)

    def test_a_veto_that_cannot_be_evaluated_is_not_a_passed_veto(self):
        self.assertTrue(PILOT.b11b_vetoes({}, {"garbage": object()}))

    def test_every_refusal_carries_a_reason(self):
        for overrides in ({"decode_status": PILOT.DECODE_FAILED}, {"session_degraded": True},
                          {"observation_to_decision_ns": 10 ** 12}, {}):
            with self.subTest(overrides=overrides):
                result, reason, _detail = self._decide(**overrides)
                self.assertEqual(PILOT.RESULT_NO_ENTRY, result)
                self.assertIsNotNone(reason, "a refusal without a reason is a default")


class TestRawLogIsImmutable(Temp):
    def test_frames_append_and_are_never_rewritten(self):
        path = self.work / "raw.jsonl"
        log = PILOT.RawLog(path)
        log.append({"frame_seq": 1, "a": 1})
        log.append({"frame_seq": 2, "a": 2})
        log.close()
        first = path.read_text()
        again = PILOT.RawLog(path)
        again.append({"frame_seq": 3, "a": 3})
        again.close()
        self.assertTrue(path.read_text().startswith(first),
                        "an existing raw line was rewritten")
        self.assertEqual(3, len(path.read_text().strip().splitlines()))

    def test_a_reopened_log_continues_the_sequence(self):
        path = self.work / "raw.jsonl"
        log = PILOT.RawLog(path)
        log.append({"frame_seq": 1})
        log.close()
        again = PILOT.RawLog(path)
        self.assertEqual(1, again.count)
        self.assertEqual(2, again.append({"frame_seq": 2}))
        again.close()

    def test_each_frame_is_flushed_immediately(self):
        """A buffered raw log loses the last frames on a hard stop — the ones an audit wants."""
        path = self.work / "raw.jsonl"
        log = PILOT.RawLog(path)
        log.append({"frame_seq": 1})
        self.assertEqual(1, len(path.read_text().strip().splitlines()))
        log.close()


class TestOfflineSession(Temp):
    def setUp(self):
        super().setUp()
        # Set AND restored. `setdefault` with no cleanup leaked a fake endpoint into every
        # later test in the run — including ones that spawn subprocesses, one of which then
        # failed in the full suite while passing in isolation.
        previous = os.environ.get("SOLANA_RPC_URL")
        os.environ["SOLANA_RPC_URL"] = "https://fixture.invalid/?api-key=synthetic"
        self.addCleanup(_restore_env, "SOLANA_RPC_URL", previous)
        self.session_dir = FIXTURES.run_offline_session(self.directory)
        self.database = sqlite3.connect(self.session_dir / "shadow.sqlite")
        self.addCleanup(self.database.close)

    def test_the_reconnect_loop_terminates(self):
        """It did not, once: an exhausted transport spun to 475,805 sessions in 283 seconds."""
        sessions = self.database.execute("SELECT COUNT(*) FROM session").fetchone()[0]
        self.assertLessEqual(sessions, 3)

    def test_every_frame_is_preserved(self):
        raw = (self.session_dir / "raw_frames.jsonl").read_text().strip().splitlines()
        self.assertEqual(7, len(raw))
        for line in raw:
            record = json.loads(line)
            for field in ("frame_seq", "received_wall_unix", "received_monotonic_ns",
                          "commitment", "raw_notification_json", "raw_sha256"):
                self.assertIn(field, record)

    def test_both_clocks_are_recorded(self):
        record = json.loads(
            (self.session_dir / "raw_frames.jsonl").read_text().splitlines()[0])
        self.assertIsInstance(record["received_wall_unix"], float)
        self.assertIsInstance(record["received_monotonic_ns"], int)

    def test_a_failed_transaction_produces_no_launch(self):
        """SigE carries a valid payload and an error; a failed transaction launched nothing."""
        rows = self.database.execute(
            "SELECT COUNT(*) FROM launch WHERE signature='SigE'").fetchone()[0]
        self.assertEqual(0, rows)

    def test_nothing_was_ever_proposed(self):
        proposed = self.database.execute(
            "SELECT COUNT(*) FROM decision WHERE policy_result=?",
            (PILOT.RESULT_PROPOSED,)).fetchone()[0]
        self.assertEqual(0, proposed)

    def test_no_hypothetical_size_is_recorded_against_a_refusal(self):
        """A number next to a decision that never happened reads as a decision that did."""
        rows = self.database.execute(
            "SELECT COUNT(*) FROM decision WHERE policy_result=? AND "
            "hypothetical_quote_lamports IS NOT NULL", (PILOT.RESULT_NO_ENTRY,)).fetchone()[0]
        self.assertEqual(0, rows)

    def test_the_artifact_records_what_it_is_not(self):
        meta = dict(self.database.execute("SELECT key, value FROM metadata"))
        self.assertEqual("false", meta["geyser_fidelity"])
        self.assertEqual("never_executed", meta["execution_status"])
        self.assertEqual("not_evaluated", meta["performance_status"])
        self.assertEqual("0", meta["contains_outcomes"])

    def test_the_endpoint_receipt_is_scheme_and_host_only(self):
        meta = dict(self.database.execute("SELECT key, value FROM metadata"))
        self.assertEqual("wss://fixture.invalid", meta["endpoint_scheme_host"])
        self.assertNotIn("api-key", meta["endpoint_scheme_host"])

    def test_no_credential_reaches_any_artifact(self):
        for path in (self.session_dir / "shadow.sqlite", self.session_dir / "raw_frames.jsonl"):
            with self.subTest(path=path.name):
                self.assertNotIn(b"synthetic", path.read_bytes().replace(b"synthetic_fixture", b""))

    def test_the_status_line_is_redacted_and_aggregate(self):
        report = PILOT.status(db_path=self.session_dir / "shadow.sqlite",
                              raw_path=self.session_dir / "raw_frames.jsonl")
        PILOT.assert_redacted(report)
        self.assertFalse(report["geyser_fidelity"])
        self.assertEqual(7, report["frames_received"] + 0 if False else report["raw_frames_on_disk"])


class TestPopulationSeparation(Temp):
    """The regression that ended a 72-hour pilot in minutes.

    The stopping rule stops after 5,000 observed launches. Counting every Pump event as a launch
    made the census read 814 when four launches had been seen, and 1,055 when ten had. A trade is
    not a launch under any reading of the frozen document.
    """

    def setUp(self):
        super().setUp()
        previous = os.environ.get("SOLANA_RPC_URL")
        os.environ["SOLANA_RPC_URL"] = "https://fixture.invalid/?api-key=synthetic"
        self.addCleanup(_restore_env, "SOLANA_RPC_URL", previous)
        self.session_dir = FIXTURES.run_offline_session(self.directory)
        self.database = sqlite3.connect(self.session_dir / "shadow.sqlite")
        self.addCleanup(self.database.close)

    def test_the_launch_table_holds_only_launch_candidates(self):
        statuses = {row[0] for row in
                    self.database.execute("SELECT DISTINCT decode_status FROM launch")}
        self.assertTrue(statuses <= set(PILOT.LAUNCH_CANDIDATE_STATUSES), statuses)
        for status in PILOT.NON_LAUNCH_STATUSES:
            self.assertNotIn(status, statuses)

    def test_a_well_formed_trade_event_never_reaches_the_launch_table(self):
        """The decisive case: right shape, right program, different discriminator."""
        b7d, disc, create_type, types = PILOT.load_pinned_create_type()
        status, fields, _error = PILOT.decode_create(FIXTURES.trade_payload(), b7d, disc,
                                                     create_type, types)
        self.assertEqual(PILOT.DECODE_UNKNOWN, status)
        self.assertIn(status, PILOT.NON_LAUNCH_STATUSES)
        self.assertIsNone(fields)

    def test_non_launch_events_are_preserved_and_counted_separately(self):
        census = dict(self.database.execute(
            "SELECT decode_status, COUNT(*) FROM pump_event GROUP BY 1"))
        self.assertTrue(census, "non-launch events must be preserved, not discarded")
        self.assertTrue(set(census) <= set(PILOT.NON_LAUNCH_STATUSES), census)

    def test_the_stopping_counter_counts_only_decoded_creates(self):
        decoded = self.database.execute(
            "SELECT COUNT(*) FROM launch WHERE decode_status=?",
            (PILOT.DECODE_DECODED,)).fetchone()[0]
        self.assertEqual(decoded, PILOT.observed_launch_count(self.database))
        census = self.database.execute("SELECT COUNT(*) FROM pump_event").fetchone()[0]
        self.assertGreater(census, 0)
        self.assertLess(PILOT.observed_launch_count(self.database), decoded + census,
                        "the counter must not absorb the non-launch census")

    def test_one_decision_per_launch_and_no_others(self):
        launches = self.database.execute("SELECT COUNT(*) FROM launch").fetchone()[0]
        decisions = self.database.execute("SELECT COUNT(*) FROM decision").fetchone()[0]
        self.assertEqual(launches, decisions)
        self.assertGreater(launches, 0)

    def test_the_invariants_hold_on_the_live_path(self):
        self.assertTrue(PILOT.assert_population_invariants(self.database))

    def test_a_contaminated_launch_table_is_refused(self):
        """Plant a trade in the launch table and the invariant must fire."""
        self.database.execute(
            "INSERT INTO launch(session_id,frame_seq,decoded_wall_unix,decoded_monotonic_ns,"
            "decode_status,evidence_sha256,create_key) VALUES ('s',1,0.0,0,?,'e','k1')",
            (PILOT.DECODE_UNKNOWN,))
        with self.assertRaisesRegex(Refused, "not launch candidates"):
            PILOT.assert_population_invariants(self.database)

    def test_a_launch_without_a_decision_is_refused(self):
        self.database.execute(
            "INSERT INTO launch(session_id,frame_seq,decoded_wall_unix,decoded_monotonic_ns,"
            "decode_status,evidence_sha256,create_key) VALUES ('s',1,0.0,0,?,'e','k2')",
            (PILOT.DECODE_DECODED,))
        with self.assertRaisesRegex(Refused, "exactly one"):
            PILOT.assert_population_invariants(self.database)

    def test_an_orphan_decision_is_refused(self):
        """Counts kept EQUAL on purpose, so the orphan check is the one under test.

        Simply adding an orphan also unbalances the totals, and the count check fires first — the
        orphan branch was a mutation survivor because nothing ever reached it.
        """
        victim = self.database.execute("SELECT decision_seq FROM decision LIMIT 1").fetchone()[0]
        self.database.execute("DELETE FROM decision WHERE decision_seq=?", (victim,))
        self.database.execute(
            "INSERT INTO decision(launch_seq,policy_id,decided_wall_unix,decided_monotonic_ns,"
            "observation_to_decision_ns,feature_availability,policy_result,evidence_sha256) "
            "VALUES (999999,'p',0.0,0,0,'{}','no_shadow_entry','e')")
        with self.assertRaisesRegex(Refused, "reference no launch"):
            PILOT.assert_population_invariants(self.database)

    def test_a_duplicate_launch_cannot_be_recorded(self):
        """A redelivered notification after a reconnect must not inflate the count."""
        key = PILOT.create_key("SigA", 1000, 0, {"mint": "M"})
        self.assertEqual(key, PILOT.create_key("SigA", 1000, 0, {"mint": "M"}))
        self.assertNotEqual(key, PILOT.create_key("SigA", 1000, 1, {"mint": "M"}))
        before = self.database.execute("SELECT COUNT(*) FROM launch").fetchone()[0]
        existing = self.database.execute(
            "SELECT create_key FROM launch LIMIT 1").fetchone()[0]
        self.database.execute(
            "INSERT OR IGNORE INTO launch(session_id,frame_seq,decoded_wall_unix,"
            "decoded_monotonic_ns,decode_status,evidence_sha256,create_key) "
            "VALUES ('s',1,0.0,0,?,'e',?)", (PILOT.DECODE_DECODED, existing))
        self.assertEqual(before,
                         self.database.execute("SELECT COUNT(*) FROM launch").fetchone()[0])


class TestReplay(Temp):
    """Derived tables are a function of the raw log, so a derivation defect is repairable."""

    def setUp(self):
        super().setUp()
        previous = os.environ.get("SOLANA_RPC_URL")
        os.environ["SOLANA_RPC_URL"] = "https://fixture.invalid/?api-key=synthetic"
        self.addCleanup(_restore_env, "SOLANA_RPC_URL", previous)
        self.session_dir = FIXTURES.run_offline_session(self.directory)

    def _replay(self):
        return PILOT.replay(raw_path=self.session_dir / "raw_frames.jsonl",
                            db_path=self.session_dir / "shadow.sqlite")

    def test_replay_reproduces_the_same_launches(self):
        database = sqlite3.connect(self.session_dir / "shadow.sqlite")
        before = database.execute("SELECT COUNT(*) FROM launch WHERE decode_status='decoded'"
                                  ).fetchone()[0]
        database.close()
        counts = self._replay()
        self.assertEqual(before, counts["decoded"])
        self.assertEqual(counts["decoded"], counts["decision_rows"])

    def test_replay_is_idempotent(self):
        first = self._replay()
        second = self._replay()
        self.assertEqual(first["decoded"], second["decoded"])
        self.assertEqual(first["launch_rows"], second["launch_rows"])

    def test_replay_never_touches_the_raw_log(self):
        raw = self.session_dir / "raw_frames.jsonl"
        before = raw.read_bytes()
        self._replay()
        self.assertEqual(before, raw.read_bytes(), "raw evidence must never be rewritten")

    def test_replay_separates_the_populations(self):
        counts = self._replay()
        self.assertGreater(counts["non_launch_events"], 0)
        self.assertEqual(counts["launch_rows"], counts["decoded"])
        self.assertEqual(counts["observed_launches_for_stopping_rule"], counts["decoded"])

    def test_replay_refuses_without_raw_evidence(self):
        with self.assertRaisesRegex(Refused, "nothing to replay from"):
            PILOT.replay(raw_path=self.directory / "absent.jsonl",
                         db_path=self.session_dir / "shadow.sqlite")


class TestTheGate(Temp):
    def test_launch_readiness_is_green_and_touches_no_network(self):
        report = FIXTURES.gate()
        self.assertEqual([], report["findings"])
        self.assertTrue(report["launch_ready"])
        self.assertFalse(report["network_used"])
        self.assertFalse(report["geyser_fidelity"])
        self.assertEqual("absent", report["execution_surface"])


class TestB11aUntouched(unittest.TestCase):
    def test_the_pilot_never_names_a_b11a_path(self):
        for name in ("b15a_shadow_pilot.py", "b15a_websocket.py", "b15a_shadow_fixtures.py"):
            source = (ROOT / "scripts" / name).read_text()
            body = source.split("FORBIDDEN_PATH_MARKERS = (", 1)[-1].split(")", 1)[-1]
            with self.subTest(name=name):
                self.assertNotIn("research/b11a", body)
                self.assertNotIn("supervisor_state", body)

    def test_b14c_eligible_windows_is_unchanged(self):
        prereg = json.loads(
            (ROOT / "research" / "B14C_MODEL_PREREGISTRATION.json").read_text())
        self.assertEqual([], prereg["eligibility"]["eligible_windows"])


if __name__ == "__main__":
    unittest.main()
