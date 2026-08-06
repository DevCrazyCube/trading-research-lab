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
