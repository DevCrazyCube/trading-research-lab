"""Guards for the B18a shadow record layer.

The layer's whole value is that a record means exactly what the frozen contract says. So these
tests attack the two rules the contract exists to enforce -- unknown is never zero, and landing
probability is forbidden -- plus the things that would quietly make a shadow record incomparable to
a live one, or would let this layer alter the recorder it reads.

Fixtures are built with the RECORDER'S OWN SegmentWriter rather than a hand-rolled imitation of its
framing. A test that reads a format the test itself invented proves only that the test agrees with
itself.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import pathlib
import socket
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B18A = _load("b18a_shadow_record_under_test", "b18a_shadow_record.py")
RECORDER = _load("recorder_for_b18a_tests", "recorder.py")

DECISION = {"decision_unix_nanos": 1_786_000_000_100_000, "retry_policy_id": "RP1"}
ENDPOINT = "https://user:pw@rpc.example.com:8899/secret/path?key=v"
CLOCK_SOURCE = "CLOCK_REALTIME, not monotonic"


def _header(seq):
    return {"recorder_id": "REC01", "session_id": "SESS01", "seq_in_session": seq,
            "provider_seq": None, "provider_message_id": None,
            "received_at_mono_ns": 1_000 + seq,
            "received_at_wall_ns": 1_786_000_000_000_000 + seq,
            "payload_encoding": "json", "payload_schema_version": "b6-lite-normalized-v1",
            "provider_kind": "rpc_http", "subscription_id": "abc123"}


class SegmentFixture(unittest.TestCase):
    """A real recorder segment, written by the recorder's own writer."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = self._directory.name

    def write_segment(self, slots=(435_600_001, 435_600_002, 435_600_003), payloads=None):
        writer = RECORDER.SegmentWriter(self.root, "REC01", "SESS01")
        for seq, slot in enumerate(slots):
            payload = payloads[seq] if payloads else json.dumps({"slot": slot}).encode()
            writer.write(seq, _header(seq), payload)
        return writer.seal(len(slots) - 1)

    def one_record(self, **kwargs):
        observation = B18A.observation_from_frame(B18A.read_frames(self.write_segment())[0])
        return B18A.emit(observation, DECISION, ENDPOINT, clock_source=CLOCK_SOURCE, **kwargs)


# ----------------------------------------------------------------------------------------------
# The contract is read and pinned, not restated
# ----------------------------------------------------------------------------------------------

class ContractPinningTests(unittest.TestCase):

    def test_the_field_list_comes_from_the_document(self):
        """If these were retyped they would drift, so they are derived and this proves it."""
        document = json.loads(B18A.CONTRACT_PATH.read_text())
        expected = [entry["name"] for entry in document["clocks"]["fields"]]
        for name in expected:
            self.assertIn(name, B18A.MEASURED_FIELDS)
        self.assertEqual(B18A.REASON_CODES,
                         tuple(e["code"] for e in document["unmeasured_reason_codes"]))

    def test_a_tampered_contract_refuses_to_load(self):
        """Records written against an edited contract claim a conformance nobody froze."""
        document = json.loads(B18A.CONTRACT_PATH.read_text())
        document["clocks"]["fields"].append({"name": "invented_clock", "nullable": True})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(document, handle)
            path = pathlib.Path(handle.name)
        self.addCleanup(path.unlink)
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.load_contract(path)
        self.assertIn("has changed", str(refusal.exception))

    def test_a_missing_contract_refuses_rather_than_defaulting(self):
        with self.assertRaises(B18A.RecordRefused):
            B18A.load_contract(ROOT / "research" / "no_such_contract.json")

    def test_the_pinned_hash_matches_the_document_on_disk(self):
        document = json.loads(B18A.CONTRACT_PATH.read_text())
        self.assertEqual(B18A.canonical_sha256(document), B18A.CONTRACT_SHA256)

    def test_the_pin_is_canonical_and_deliberately_not_the_file_hash(self):
        """An auditor re-checked the pin with `sha256sum` and read the mismatch as tampering.

        The pin is over canonical serialization so it survives reindentation and key reordering --
        the contract's MEANING is frozen, not its whitespace. Both values are asserted here so the
        difference is a documented fact rather than a surprise, and so that a reformatting of the
        file fails this test loudly instead of silently invalidating the reference value.
        """
        file_digest = hashlib.sha256(B18A.CONTRACT_PATH.read_bytes()).hexdigest()
        self.assertEqual(file_digest, B18A.CONTRACT_FILE_SHA256_FOR_REFERENCE)
        self.assertNotEqual(file_digest, B18A.CONTRACT_SHA256)

    def test_canonical_hashing_ignores_formatting_but_not_content(self):
        """Why the pin is canonical, demonstrated rather than asserted."""
        document = json.loads(B18A.CONTRACT_PATH.read_text())
        reindented = json.loads(json.dumps(document, indent=7, sort_keys=False))
        self.assertEqual(B18A.canonical_sha256(reindented), B18A.CONTRACT_SHA256)
        changed = json.loads(json.dumps(document))
        changed["contract_id"] = "SOMETHING_ELSE"
        self.assertNotEqual(B18A.canonical_sha256(changed), B18A.CONTRACT_SHA256)


# ----------------------------------------------------------------------------------------------
# Rule 1: unknown is null, never zero, and never silent
# ----------------------------------------------------------------------------------------------

class UnknownIsNeverZeroTests(SegmentFixture):

    def test_every_null_field_carries_a_reason_code(self):
        record = self.one_record()
        for field, value in record["measured"].items():
            if value is None:
                with self.subTest(field=field):
                    self.assertIn(field, record["unmeasured"])
                    self.assertIn(record["unmeasured"][field], B18A.REASON_CODES)

    def test_no_unmeasured_field_was_defaulted_to_zero_or_false(self):
        """The failure this rule exists to prevent, checked on the field that would flatter most."""
        record = self.one_record()
        for field in ("jito_tip_lamports", "base_fee_lamports", "total_execution_cost_lamports",
                      "priority_fee_lamports_paid", "slippage_tokens"):
            with self.subTest(field=field):
                self.assertIsNone(record["measured"][field])
                self.assertNotEqual(record["measured"][field], 0)

    def test_a_null_without_a_reason_is_refused(self):
        record = self.one_record()
        del record["unmeasured"]["jito_tip_lamports"]
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("no reason code", str(refusal.exception))

    def test_a_reason_attached_to_a_known_value_is_refused(self):
        """The lie in the other direction: claiming something is unmeasured when it is right there."""
        record = self.one_record()
        record["unmeasured"]["observation_slot"] = "U_NOT_INSTRUMENTED"
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("value AND a reason", str(refusal.exception))

    def test_a_reason_code_outside_the_frozen_set_is_refused(self):
        record = self.one_record()
        record["unmeasured"]["jito_tip_lamports"] = "U_PROBABLY_FINE"
        with self.assertRaises(B18A.RecordRefused):
            B18A.assert_conforms(record)

    def test_impossible_shadow_fields_say_not_applicable_not_uninstrumented(self):
        """`could not exist` and `nobody wired it up` are different facts and must stay different."""
        record = self.one_record()
        for field in ("send_unix_nanos", "sign_completed_unix_nanos", "land_slot",
                      "jito_tip_lamports"):
            with self.subTest(field=field):
                self.assertEqual(record["unmeasured"][field], "U_NOT_APPLICABLE")

    def test_a_non_nullable_field_may_not_be_null(self):
        record = self.one_record()
        record["measured"]["outcome"] = None
        record["unmeasured"]["outcome"] = "U_NOT_INSTRUMENTED"
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("non-nullable", str(refusal.exception))

    def test_an_outcome_outside_the_frozen_enum_is_refused(self):
        """Checked on a NON-shadow stage, so only the enum rule can be what refuses it.

        On a shadow record the stage rule ("outcome must be never_sent or unknown") fires first and
        this test passed with the enum check deleted -- a mutation caught it. A test killed by a
        different guard than the one it names is not testing that guard.
        """
        record = self.one_record()
        record["stage"] = "devnet"
        record["measured"]["outcome"] = "probably_landed"
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("frozen enum", str(refusal.exception))

    def test_a_record_missing_a_contract_named_field_is_refused(self):
        """Fields do not become optional by being left out; absence is refusal, not a default."""
        record = self.one_record()
        del record["measured"]["expected_tokens_out"]
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("absent from the record", str(refusal.exception))


# ----------------------------------------------------------------------------------------------
# Rule 2: landing probability is forbidden, actively
# ----------------------------------------------------------------------------------------------

class LandingProbabilityIsForbiddenTests(SegmentFixture):

    def test_a_landing_probability_field_is_refused_by_name(self):
        record = self.one_record()
        record["landing_probability"] = 1
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("landing-probability", str(refusal.exception))

    def test_it_is_refused_under_a_new_spelling(self):
        """Refusal by suffix as well as by name, so renaming it does not smuggle it in."""
        for name in ("land_success_likelihood", "fill_odds", "inclusion_probability"):
            with self.subTest(name=name):
                record = self.one_record()
                record[name] = 1
                with self.assertRaises(B18A.RecordRefused):
                    B18A.assert_conforms(record)

    def test_it_is_refused_when_nested_rather_than_top_level(self):
        record = self.one_record()
        record["provenance"]["p_land"] = 1
        with self.assertRaises(B18A.RecordRefused):
            B18A.assert_conforms(record)

    def test_the_contract_itself_declares_no_such_field(self):
        self.assertNotIn("landing_probability", B18A.MEASURED_FIELDS)


# ----------------------------------------------------------------------------------------------
# Cost, slippage, retries, endpoint
# ----------------------------------------------------------------------------------------------

class ConformanceTests(SegmentFixture):

    def test_a_conforming_record_is_accepted(self):
        self.assertTrue(B18A.assert_conforms(self.one_record()))

    def test_a_total_cost_with_an_unknown_component_is_refused(self):
        """A partial total is worse than none, because it reads as a complete one."""
        record = self.one_record()
        record["measured"]["total_execution_cost_lamports"] = 5000
        del record["unmeasured"]["total_execution_cost_lamports"]
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("while", str(refusal.exception))

    def test_a_total_that_does_not_equal_its_components_is_refused(self):
        record = self.one_record()
        for field, value in (("base_fee_lamports", 5000), ("priority_fee_lamports_paid", 100_000),
                             ("jito_tip_lamports", 0), ("ata_rent_lamports", 2_039_280)):
            record["measured"][field] = value
            del record["unmeasured"][field]
        record["measured"]["total_execution_cost_lamports"] = 1
        del record["unmeasured"]["total_execution_cost_lamports"]
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("does not equal", str(refusal.exception))

    def test_a_total_equal_to_its_fully_known_components_is_accepted(self):
        """The rule must be satisfiable, or it is a ban wearing a condition."""
        record = self.one_record()
        components = {"base_fee_lamports": 5000, "priority_fee_lamports_paid": 100_000,
                      "jito_tip_lamports": 0, "ata_rent_lamports": 2_039_280}
        for field, value in components.items():
            record["measured"][field] = value
            del record["unmeasured"][field]
        record["measured"]["total_execution_cost_lamports"] = sum(components.values())
        del record["unmeasured"]["total_execution_cost_lamports"]
        self.assertTrue(B18A.assert_conforms(record))

    def test_a_known_zero_tip_is_distinguishable_from_an_unmeasured_one(self):
        """0 means measured-and-zero; null means not measured. The contract turns on this."""
        record = self.one_record()
        self.assertIsNone(record["measured"]["jito_tip_lamports"])
        record["measured"]["jito_tip_lamports"] = 0
        del record["unmeasured"]["jito_tip_lamports"]
        self.assertTrue(B18A.assert_conforms(record))

    def test_the_endpoint_is_stripped_of_credentials(self):
        """b9d once wrote a provider path credential into a collected artifact. Not again."""
        record = self.one_record()
        identity = record["measured"]["endpoint_identity"]
        self.assertEqual(identity, "https://rpc.example.com:8899")
        for secret in ("user", "pw", "secret", "path", "key=v"):
            self.assertNotIn(secret, identity)

    def test_an_unsanitized_endpoint_in_a_record_is_refused(self):
        record = self.one_record()
        record["measured"]["endpoint_identity"] = "https://user:pw@rpc.example.com/secret"
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("not sanitized", str(refusal.exception))

    def test_a_retry_is_its_own_record_and_names_what_it_retried(self):
        first = self.one_record()
        second = B18A.retry_record(first, retry_of_signature="SIG-A", decision=DECISION,
                                   endpoint=ENDPOINT, clock_source=CLOCK_SOURCE)
        self.assertEqual(first["measured"]["attempt_index"], 0)
        self.assertEqual(second["measured"]["attempt_index"], 1)
        self.assertEqual(second["measured"]["retry_of_signature"], "SIG-A")
        self.assertNotIn("retry_of_signature", second["unmeasured"])
        self.assertTrue(B18A.assert_conforms(second))

    def test_a_retry_that_names_nothing_is_refused(self):
        first = self.one_record()
        with self.assertRaises(B18A.RecordRefused):
            B18A.retry_record(first, retry_of_signature="", decision=DECISION,
                              endpoint=ENDPOINT, clock_source=CLOCK_SOURCE)

    def test_a_later_attempt_without_a_retry_link_is_refused(self):
        record = self.one_record()
        record["measured"]["attempt_index"] = 3
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("what was retried", str(refusal.exception))

    def test_a_negative_attempt_index_is_refused(self):
        observation = B18A.observation_from_frame(B18A.read_frames(self.write_segment())[0])
        with self.assertRaises(B18A.RecordRefused):
            B18A.emit(observation, DECISION, ENDPOINT, clock_source=CLOCK_SOURCE, attempt_index=-1)

    def test_a_float_anywhere_is_refused(self):
        record = self.one_record()
        record["measured"]["expected_tokens_out"] = 1.5
        del record["unmeasured"]["expected_tokens_out"]
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("float", str(refusal.exception))

    def test_a_field_the_contract_does_not_name_is_refused(self):
        record = self.one_record()
        record["measured"]["vibes"] = 1
        with self.assertRaises(B18A.RecordRefused):
            B18A.assert_conforms(record)

    def test_a_record_against_another_contract_revision_is_refused(self):
        record = self.one_record()
        record["contract_sha256"] = "0" * 64
        with self.assertRaises(B18A.RecordRefused):
            B18A.assert_conforms(record)


# ----------------------------------------------------------------------------------------------
# Shadow and live are the same shape, and shadow cannot pretend to have sent anything
# ----------------------------------------------------------------------------------------------

class ShadowShapeTests(SegmentFixture):

    def test_a_shadow_record_has_every_field_a_live_record_would(self):
        """If the shapes differed, no shadow measurement could ever be compared to a live one."""
        self.assertEqual(set(self.one_record()["measured"]), B18A.live_shape_reference())

    def test_a_shadow_record_claiming_it_sent_something_is_refused(self):
        for field in ("send_unix_nanos", "sign_completed_unix_nanos", "land_unix_nanos"):
            with self.subTest(field=field):
                record = self.one_record()
                record["measured"][field] = 1_786_000_000_200_000
                del record["unmeasured"][field]
                with self.assertRaises(B18A.RecordRefused) as refusal:
                    B18A.assert_conforms(record)
                self.assertIn("SHADOW record", str(refusal.exception))

    def test_a_shadow_record_may_not_claim_it_landed(self):
        record = self.one_record()
        record["measured"]["outcome"] = "landed"
        with self.assertRaises(B18A.RecordRefused):
            B18A.assert_conforms(record)

    def test_the_record_never_claims_to_be_evaluation_or_execution(self):
        record = self.one_record()
        self.assertIs(record["executable"], False)
        self.assertEqual(record["performance_status"], "not_evaluated")
        self.assertEqual(record["execution_status"], "never_executed")
        self.assertEqual(record["measured"]["outcome"], "never_sent")

    def test_every_record_carries_the_counterfactual_limitations(self):
        """An aggregate built from these must not be able to shed them silently."""
        record = self.one_record()
        self.assertTrue(record["counterfactual_limitations"])
        self.assertTrue(any("did not land" in line
                            for line in record["counterfactual_limitations"]))


# ----------------------------------------------------------------------------------------------
# Reading the recorder without changing it
# ----------------------------------------------------------------------------------------------

class RecorderIsReadOnlyTests(SegmentFixture):

    def test_reading_a_segment_does_not_alter_one_byte(self):
        path = self.write_segment()
        before = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
        B18A.records_from_segment(path, DECISION, ENDPOINT, clock_source=CLOCK_SOURCE)
        after = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_the_layer_never_calls_a_recorder_writer(self):
        """Read from the AST. The brief is explicit that recorder.py must not change behaviour."""
        tree = ast.parse((ROOT / "scripts" / "b18a_shadow_record.py").read_text())
        calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for forbidden in ("RECORDER.run", "RECORDER.run_logs", "RECORDER.append_jsonl",
                          "RECORDER.SegmentWriter", "RECORDER.recover", "RECORDER.rpc"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)

    def test_frames_are_read_through_the_recorders_own_crc_check(self):
        """Not a reimplementation of the framing: the recorder's scanner decides what is valid."""
        tree = ast.parse((ROOT / "scripts" / "b18a_shadow_record.py").read_text())
        read_frames = next(node for node in ast.walk(tree)
                           if isinstance(node, ast.FunctionDef) and node.name == "read_frames")
        calls = {ast.unparse(node.func) for node in ast.walk(read_frames)
                 if isinstance(node, ast.Call)}
        self.assertIn("RECORDER.scan_segment", calls)

    def test_a_corrupt_frame_stops_the_read_rather_than_being_guessed_at(self):
        path = pathlib.Path(self.write_segment())
        data = bytearray(path.read_bytes())
        data[-5] ^= 0xFF                      # corrupt the last record's payload
        path.write_bytes(bytes(data))
        records = B18A.records_from_segment(str(path), DECISION, ENDPOINT,
                                            clock_source=CLOCK_SOURCE)
        self.assertEqual(len(records), 2)     # the two intact frames, not a repaired third

    def test_a_segment_with_no_valid_frame_is_refused_not_reported_as_empty(self):
        """An unreadable capture is not an empty one, and calling it empty turns a gap into a zero."""
        path = pathlib.Path(self.root) / "broken.seg"
        path.write_bytes(b"\xff" * 64)
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.read_frames(str(path))
        self.assertIn("not an empty capture", str(refusal.exception))

    def test_a_zero_filled_region_is_refused_rather_than_read_as_empty_records(self):
        """CRC32C of an empty body is 0, so zero bytes pass the recorder's scanner as valid records.

        True of the framing and worth knowing; a preallocated or sparse region is absence, not
        observation. Refused here rather than repaired -- recorder.py is not this layer's to change.
        """
        path = pathlib.Path(self.root) / "zeros.seg"
        path.write_bytes(b"\x00" * 64)
        # The point is that the recorder's scanner sees these zeros as valid records at all, not
        # how many fit; asserting the count would just re-derive 64 // HDR.size.
        self.assertGreater(RECORDER.scan_segment(str(path))[0], 0)
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.read_frames(str(path))
        self.assertIn("zero-length frame header", str(refusal.exception))

    def test_a_frame_without_a_slot_is_refused_rather_than_anchored_to_nothing(self):
        path = self.write_segment(slots=(1,), payloads=[json.dumps({"no_slot": True}).encode()])
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.observation_from_frame(B18A.read_frames(path)[0])
        self.assertIn("no slot", str(refusal.exception))

    def test_an_unreadable_payload_is_refused(self):
        path = self.write_segment(slots=(1,), payloads=[b"\xff\xfe not json"])
        with self.assertRaises(B18A.RecordRefused):
            B18A.observation_from_frame(B18A.read_frames(path)[0])

    def test_the_observation_carries_recorder_provenance(self):
        record = self.one_record()
        self.assertEqual(record["provenance"]["recorder_id"], "REC01")
        self.assertEqual(record["provenance"]["session_id"], "SESS01")
        self.assertEqual(record["provenance"]["payload_schema_version"], "b6-lite-normalized-v1")


# ----------------------------------------------------------------------------------------------
# Determinism and the runtime proofs
# ----------------------------------------------------------------------------------------------

class DeterminismAndSafetyTests(SegmentFixture):

    def test_the_same_input_produces_the_same_hash(self):
        first = self.one_record()
        second = self.one_record()
        self.assertEqual(first["record_sha256"], second["record_sha256"])

    def test_a_changed_field_produces_a_different_hash(self):
        record = self.one_record()
        altered = copy.deepcopy(record)
        del altered["record_sha256"]
        altered["measured"]["observation_slot"] += 1
        self.assertNotEqual(record["record_sha256"], B18A.record_hash(altered))

    def test_the_hash_ignores_private_chaining_keys(self):
        """`_observation` is machinery, not content, and must not move the hash."""
        record = self.one_record()
        without = {k: v for k, v in record.items() if k != "record_sha256"}
        self.assertEqual(record["record_sha256"], B18A.record_hash(without))

    def test_emit_refuses_the_network_at_runtime(self):
        """Not a promise in a docstring: a socket opened during emit raises."""
        opened = []
        original = socket.socket

        def watcher(*args, **kwargs):
            opened.append(1)
            return original(*args, **kwargs)

        socket.socket = watcher
        self.addCleanup(setattr, socket, "socket", original)
        self.one_record()
        self.assertEqual(opened, [])
        with B18A.B17A.NoNetwork():
            with self.assertRaises(B18A.B17A.NetworkAttempted):
                socket.socket()

    def test_the_closure_has_no_execution_surface_and_includes_the_recorder(self):
        result = B18A.assert_no_execution_surface()
        self.assertEqual(result["execution_surface_found"], {})
        self.assertIn("recorder.py", result["closure"])
        self.assertIn("not a repository-wide", result["scope"])

    def test_records_from_a_segment_keep_the_segments_own_order(self):
        """Canonical order comes from the evidence, never from insertion or a dict."""
        path = self.write_segment(slots=(435_600_007, 435_600_008, 435_600_009))
        records = B18A.records_from_segment(path, DECISION, ENDPOINT, clock_source=CLOCK_SOURCE)
        self.assertEqual([r["measured"]["observation_slot"] for r in records],
                         [435_600_007, 435_600_008, 435_600_009])


if __name__ == "__main__":
    unittest.main()


class RealDecisionWiringTests(SegmentFixture):
    """`decide_and_record` — the first B17b records carrying a measured clock.

    Every record written before this had `decision_unix_nanos` at U_NOT_INSTRUMENTED because the
    caller passed None. What matters here is not that three fields moved out of that state, but that
    they moved because something measured them: reducing the unmeasured count by filling fields with
    plausible values is the exact failure the contract exists to prevent, and it would look
    identical from the outside.
    """

    def setUp(self):
        super().setUp()
        synthetic = B18A.B17A.synthetic_observation()
        self.curve_state = B18A.B17A.curve_state(synthetic) | {
            k: synthetic[k] for k in ("mint", "bonding_curve", "creator")}
        self.components = copy.deepcopy(B18A.B17A.B12B.demo_components())

    def record(self, components=None, curve_state=None, clock=None):
        observation = B18A.observation_from_frame(B18A.read_frames(self.write_segment())[0])
        return B18A.decide_and_record(
            observation, curve_state or self.curve_state, components or self.components,
            ENDPOINT, clock_source=CLOCK_SOURCE, quote_lamports=100_000_000,
            **({"clock": clock} if clock else {}))

    def test_the_decision_clock_is_measured_not_supplied(self):
        record = self.record(clock=lambda: 1_786_000_000_123_456_789)
        self.assertEqual(record["measured"]["decision_unix_nanos"], 1_786_000_000_123_456_789)
        self.assertNotIn("decision_unix_nanos", record["unmeasured"])

    def test_the_clock_is_taken_around_the_decision_not_at_the_observation(self):
        """A decision clock equal to the observation clock would be a copied timestamp."""
        record = self.record()
        self.assertNotEqual(record["measured"]["decision_unix_nanos"],
                            record["measured"]["observation_unix_nanos"])
        self.assertGreater(record["measured"]["decision_unix_nanos"],
                           record["measured"]["observation_unix_nanos"])

    def test_the_quoted_state_slot_is_the_curve_the_decision_saw(self):
        record = self.record()
        self.assertEqual(record["measured"]["quoted_state_slot"], self.curve_state["slot"])

    def test_an_approved_decision_carries_a_price(self):
        record = self.record()
        self.assertEqual(record["provenance"]["risk_decision"]["decision"], "approved")
        self.assertGreater(record["measured"]["expected_tokens_out"], 0)

    def test_a_rejected_decision_is_never_priced(self):
        """B17a's seam, enforced here too: a price for a refused order describes a decision nobody
        made. This is the property that must survive, not the field count."""
        components = copy.deepcopy(self.components)
        components["health"]["kill_switch_engaged"] = True
        record = self.record(components=components)
        self.assertEqual(record["provenance"]["risk_decision"]["decision"], "rejected")
        self.assertEqual(record["provenance"]["risk_decision"]["primary_reason"],
                         "R02_KILL_SWITCH_ENGAGED")
        self.assertIsNone(record["measured"]["expected_tokens_out"])
        self.assertEqual(record["unmeasured"]["expected_tokens_out"], "U_NOT_INSTRUMENTED")

    def test_a_rejected_decision_still_records_its_clock(self):
        """A refusal is a decision and it happened at a time. Losing that would make refusals
        invisible to any later latency question."""
        components = copy.deepcopy(self.components)
        components["health"]["kill_switch_engaged"] = True
        record = self.record(components=components)
        self.assertIsNotNone(record["measured"]["decision_unix_nanos"])

    def test_exactly_four_fields_remain_uninstrumented_and_each_has_a_reason(self):
        """The count is not the point; these four are the ones nothing measured."""
        record = self.record()
        remaining = sorted(k for k, v in record["unmeasured"].items()
                           if v == "U_NOT_INSTRUMENTED")
        self.assertEqual(remaining, ["provider_region_declared", "retry_policy_id", "route",
                                     "slippage_limit_tokens"])

    def test_no_unratified_policy_identifier_was_invented(self):
        """retry_policy_id and slippage_limit_tokens name things that do not exist. Writing an
        identifier for a policy nobody ratified would be inventing the policy."""
        record = self.record()
        self.assertIsNone(record["measured"]["retry_policy_id"])
        self.assertIsNone(record["measured"]["slippage_limit_tokens"])

    def test_a_recorder_observation_alone_cannot_support_a_decision(self):
        """The finding that forced curve_state to be a separate argument: a recorder frame carries
        no decoded reserves, so the decode step is missing rather than implicit."""
        observation = B18A.observation_from_frame(B18A.read_frames(self.write_segment())[0])
        for field in ("virtual_quote", "virtual_token", "real_quote", "real_token"):
            self.assertNotIn(field, observation)
        with self.assertRaises((KeyError, TypeError)):
            B18A.decide_and_record(observation, observation, self.components, ENDPOINT,
                                   clock_source=CLOCK_SOURCE, quote_lamports=100_000_000)

    def test_the_proposal_id_names_recorder_coordinates_not_a_transaction_index(self):
        """seq_in_session is a frame counter. Calling it a transaction index would have put a wrong
        name in the identifier of every record."""
        tree = ast.parse((ROOT / "scripts" / "b18a_shadow_record.py").read_text())
        builder = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "_proposal_from")
        # Docstring excluded. The docstring EXPLAINS why transaction_index would be wrong, so a scan
        # that reads it trips on its own reasoning -- the same self-reference trap b17a's surface
        # scanner hit, and the same fix: a name in prose is documentation, in code it is a choice.
        body = [n for n in builder.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))]
        source = "\n".join(ast.unparse(n) for n in body)
        self.assertIn("observation_slot", source)
        self.assertIn("seq_in_session", source)
        self.assertNotIn("transaction_index", source)

    def test_the_proposal_builder_carries_no_strategy(self):
        """Held to the same standard as b17a's propose: no branch, no numeric constant."""
        tree = ast.parse((ROOT / "scripts" / "b18a_shadow_record.py").read_text())
        builder = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "_proposal_from")
        self.assertEqual([n for n in ast.walk(builder)
                          if isinstance(n, (ast.If, ast.Compare))], [])
        self.assertEqual([n.value for n in ast.walk(builder)
                          if isinstance(n, ast.Constant)
                          and isinstance(n.value, (int, float))
                          and not isinstance(n.value, bool)], [])

    def test_the_record_still_conforms_and_is_still_a_shadow_record(self):
        record = self.record()
        self.assertTrue(B18A.assert_conforms(record))
        self.assertEqual(record["stage"], "shadow")
        self.assertEqual(record["measured"]["outcome"], "never_sent")


class ArtifactsMatchTheCodeTests(unittest.TestCase):
    """The committed evidence files must say what the code produces.

    6d01eba changed the code and both sweep declarations and left these two artifacts stale, so
    research/b18a/records.json showed seven uninstrumented fields while the commit message said
    four. In this repository the artifacts ARE the evidence -- the gap map and the inventory cite
    them by path -- so a reader checking the message against the file concludes the message is
    wrong. Worse than stale: `main()` still hardcoded the decision to None, so the CLI could not
    produce the new records at all and regenerating would have changed nothing.

    These tests fail if an artifact drifts from the code again, which is cheaper than remembering.
    """

    def test_the_frame_only_artifact_reports_seven_uninstrumented(self):
        report = json.loads((ROOT / "research/b18a/records.json").read_text())
        self.assertFalse(report["decision_backed"])
        self.assertEqual(report["uninstrumented_count"], 7)

    def test_the_decision_backed_artifact_reports_four(self):
        report = json.loads((ROOT / "research/b18a/decision_records.json").read_text())
        self.assertTrue(report["decision_backed"])
        self.assertEqual(report["uninstrumented_count"], 4)
        self.assertEqual(report["uninstrumented_fields"],
                         ["provider_region_declared", "retry_policy_id", "route",
                          "slippage_limit_tokens"])

    def test_the_artifacts_agree_with_what_the_records_actually_carry(self):
        """The header count must be derived from the records, not asserted beside them."""
        for name in ("records", "decision_records"):
            report = json.loads((ROOT / f"research/b18a/{name}.json").read_text())
            observed = sorted({field for record in report["records"]
                               for field, reason in record["unmeasured"].items()
                               if reason == "U_NOT_INSTRUMENTED"})
            with self.subTest(artifact=name):
                self.assertEqual(report["uninstrumented_fields"], observed)
                self.assertEqual(report["uninstrumented_count"], len(observed))

    def test_the_cli_can_reach_the_decision_path(self):
        """`decide_and_record` was reachable only from the API, so the documented entry point
        could not produce a decision-backed record. An unreachable feature is an absent one."""
        tree = ast.parse((ROOT / "scripts" / "b18a_shadow_record.py").read_text())
        main = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        calls = {ast.unparse(n.func) for n in ast.walk(main) if isinstance(n, ast.Call)}
        self.assertIn("decide_and_record", calls)

    def test_the_synthetic_curve_state_says_it_is_synthetic(self):
        state = json.loads((ROOT / "research/b18a/synthetic_curve_state.json").read_text())
        self.assertIn("SYNTHETIC", state["_synthetic"])
        self.assertIn("not derived", state["_synthetic"].replace("rather than derived",
                                                                 "not derived"))


class CliProducesTheArtifactTests(SegmentFixture):
    """Run `main` and check ITS OUTPUT, rather than reading the file it wrote last time.

    The stored-artifact tests above pin what a reader sees. They cannot test the code that produces
    it: a mutant that breaks `main` leaves the committed file untouched, so they pass. Two mutants
    survived on exactly that -- disabling the curve-state branch, and hardcoding the count instead
    of deriving it.

    The general form, which is the third instance of one rule today: A TEST THAT READS A STORED
    ARTIFACT CANNOT TEST THE CODE THAT PRODUCES IT. It is the same shape as reading a harness's
    report instead of driving the subject, one layer out.
    """

    def setUp(self):
        super().setUp()
        synthetic = B18A.B17A.synthetic_observation()
        state = B18A.B17A.curve_state(synthetic) | {
            k: synthetic[k] for k in ("mint", "bonding_curve", "creator")}
        self.state_path = pathlib.Path(self.root) / "curve.json"
        self.state_path.write_text(json.dumps(state))
        self.out = pathlib.Path(self.root) / "out.json"

    def run_main(self, *extra):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            B18A.main(["--segment", self.write_segment(), "--output", str(self.out), *extra])
        return json.loads(self.out.read_text())

    def test_the_cli_without_a_curve_state_leaves_seven_uninstrumented(self):
        report = self.run_main()
        self.assertFalse(report["decision_backed"])
        self.assertEqual(report["uninstrumented_count"], 7)

    def test_the_cli_with_a_curve_state_measures_three_of_them(self):
        """Kills the mutant that ignores --curve-state: the count stays 7 without the decision."""
        report = self.run_main("--curve-state", str(self.state_path))
        self.assertTrue(report["decision_backed"])
        self.assertEqual(report["uninstrumented_count"], 4)
        for field in ("decision_unix_nanos", "quoted_state_slot", "expected_tokens_out"):
            with self.subTest(field=field):
                self.assertNotIn(field, report["uninstrumented_fields"])
                self.assertIsNotNone(report["records"][0]["measured"][field])

    def test_the_count_is_derived_from_the_records_it_shipped(self):
        """Kills the hardcoded-count mutant: the header must follow the records, in both modes."""
        for extra in ((), ("--curve-state", str(self.state_path))):
            report = self.run_main(*extra)
            observed = sorted({field for record in report["records"]
                               for field, reason in record["unmeasured"].items()
                               if reason == "U_NOT_INSTRUMENTED"})
            with self.subTest(decision_backed=report["decision_backed"]):
                self.assertEqual(report["uninstrumented_fields"], observed)
                self.assertEqual(report["uninstrumented_count"], len(observed))
