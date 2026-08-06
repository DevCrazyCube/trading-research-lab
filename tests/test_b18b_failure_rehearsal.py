"""Guards for B18b's failure rehearsals.

The harness exists because a third of B17b's vocabulary could not be reached. These tests check that
it is reached HONESTLY: that the distinctions the contract cares about survive the trip through a
fault, and that a fault record can never be mistaken for a record of something that happened.

The distinction most of these defend is the one a zero would erase -- "we know it did not happen"
against "we do not know what happened". `never_sent` and `unknown` are both failures and they are
not the same failure, and the reason codes on the land clocks are where that difference lives.
"""
import copy
import importlib.util
import json
import pathlib
import socket
import tempfile
import unittest
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B18B = _load("b18b_failure_rehearsal_under_test", "b18b_failure_rehearsal.py")
B18A = B18B.B18A
RECORDER = _load("recorder_for_b18b_tests", "recorder.py")

ENDPOINT = "https://api.mainnet-beta.solana.com"
CLOCK = "CLOCK_REALTIME via time.time_ns(); NOT monotonic"


def _record(fault, **kwargs):
    return B18B.fault_record(fault, B18B.synthetic_observation(), ENDPOINT,
                             clock_source=CLOCK, **kwargs)


def _chain(fault):
    return B18B.attempt_chain(fault, B18B.synthetic_observation(), ENDPOINT, clock_source=CLOCK)


# ----------------------------------------------------------------------------------------------
# The retry decision comes from the shared transport policy, not a copy
# ----------------------------------------------------------------------------------------------

class RetryPolicyTests(unittest.TestCase):

    def test_a_403_is_terminal_and_produces_exactly_one_record(self):
        """A 403 is the WAF refusing this client. Retrying it is how the watcher got banned."""
        chain = _chain("provider_403")
        self.assertEqual(len(chain), 1)
        self.assertFalse(B18B.is_retryable("provider_403"))

    def test_429_and_the_5xx_set_are_retried(self):
        for fault in ("provider_429", "provider_500", "provider_503"):
            with self.subTest(fault=fault):
                self.assertTrue(B18B.is_retryable(fault))
                self.assertGreater(len(_chain(fault)), 1)

    def test_a_transport_error_is_retryable_by_type_not_by_message(self):
        """A transient URLError once killed a live watcher because its message matched no marker."""
        self.assertTrue(B18B.is_retryable("dns_failure"))
        self.assertTrue(B18B.is_retryable("connection_timeout"))

    def test_the_policy_is_the_shared_module_not_a_local_table(self):
        """Read it from the module under test: a second copy of a policy drifts from the first."""
        source = (ROOT / "scripts" / "b18b_failure_rehearsal.py").read_text()
        self.assertIn("IDENTITY.is_retryable_error", source)

    def test_the_shared_policy_actually_decides_these_cases(self):
        """Not merely called: its answers are what the harness reports."""
        identity = B18B.IDENTITY
        self.assertFalse(identity.is_retryable_status(403))
        self.assertTrue(identity.is_retryable_status(429))
        self.assertTrue(identity.is_retryable_error(urllib.error.URLError("anything at all")))

    def test_a_chain_side_outcome_is_not_a_transport_retry(self):
        """`dropped` and `failed_on_chain` are chain facts; resending is a new decision, not a retry."""
        for fault in ("dropped", "expired", "failed_on_chain"):
            with self.subTest(fault=fault):
                self.assertFalse(B18B.is_retryable(fault))
                self.assertEqual(len(_chain(fault)), 1)


# ----------------------------------------------------------------------------------------------
# Every attempt is its own record
# ----------------------------------------------------------------------------------------------

class AttemptsAreSeparateRecordsTests(unittest.TestCase):

    def test_attempt_indexes_increase_and_each_names_what_it_retried(self):
        chain = _chain("provider_503")
        self.assertEqual([r["measured"]["attempt_index"] for r in chain], [0, 1, 2])
        self.assertIsNone(chain[0]["measured"]["retry_of_signature"])
        for record in chain[1:]:
            self.assertIsNotNone(record["measured"]["retry_of_signature"])

    def test_no_attempt_is_a_counter_on_a_previous_record(self):
        """Collapsing attempts hides the distribution of what it took, which is the whole point."""
        chain = _chain("provider_429")
        self.assertEqual(len({r["record_sha256"] for r in chain}), len(chain))

    def test_a_duplicated_attempt_is_refused(self):
        chain = _chain("provider_503")
        with self.assertRaises(B18B.RecordRefused) as refusal:
            B18B.assert_no_duplicate_attempts(chain + [chain[1]])
        self.assertIn("appears twice", str(refusal.exception))

    def test_distinct_attempts_are_not_mistaken_for_duplicates(self):
        """The guard must be satisfiable, or it is a ban wearing a condition."""
        self.assertTrue(B18B.assert_no_duplicate_attempts(_chain("provider_503")))


# ----------------------------------------------------------------------------------------------
# The distinction a zero would erase
# ----------------------------------------------------------------------------------------------

class UnknownIsNotTheSameAsDidNotHappenTests(unittest.TestCase):

    def test_provider_silence_leaves_the_landing_genuinely_unknown(self):
        """The request went out and nothing came back. It MAY have landed."""
        record = _record("provider_silence")
        self.assertEqual(record["measured"]["outcome"], "unknown")
        for field in ("land_unix_nanos", "land_slot", "finalize_unix_nanos"):
            with self.subTest(field=field):
                self.assertIsNone(record["measured"][field])
                self.assertEqual(record["unmeasured"][field], "U_PROVIDER_SILENT")
        self.assertEqual(record["unmeasured"]["receipt_unix_nanos"], "U_PROVIDER_SILENT")

    def test_a_dns_failure_did_not_happen_rather_than_being_unknown(self):
        """Nothing left this host, so `never_sent` is KNOWN. Absence of a send is an observation."""
        record = _record("dns_failure")
        self.assertEqual(record["measured"]["outcome"], "never_sent")
        self.assertEqual(record["unmeasured"]["send_unix_nanos"], "U_NOT_APPLICABLE")
        self.assertEqual(record["unmeasured"]["land_unix_nanos"], "U_NOT_APPLICABLE")

    def test_silence_and_never_sent_do_not_collapse_into_one_another(self):
        """The two failures are different and their records must be distinguishable."""
        silent, never = _record("provider_silence"), _record("dns_failure")
        self.assertNotEqual(silent["measured"]["outcome"], never["measured"]["outcome"])
        self.assertNotEqual(silent["unmeasured"]["land_unix_nanos"],
                            never["unmeasured"]["land_unix_nanos"])

    def test_our_lost_response_is_not_blamed_on_the_provider(self):
        """U_LOST is our defect; U_PROVIDER_SILENT is theirs. Keeping them apart is the point."""
        record = _record("lost_response")
        self.assertEqual(record["measured"]["outcome"], "unknown")
        self.assertEqual(record["unmeasured"]["receipt_unix_nanos"], "U_LOST")

    def test_a_failure_that_landed_still_carries_its_real_cost(self):
        """failed_on_chain is the one failure that cost money; recording it as dropped hides that."""
        record = _record("failed_on_chain")
        self.assertEqual(record["measured"]["outcome"], "failed_on_chain")
        self.assertIsNotNone(record["measured"]["land_slot"])
        self.assertEqual(record["measured"]["total_execution_cost_lamports"],
                         5_000 + 100_000 + 0 + 2_039_280)
        self.assertIsNotNone(record["measured"]["on_chain_error"])

    def test_a_dropped_attempt_never_landed_and_says_so_structurally(self):
        record = _record("dropped")
        self.assertEqual(record["measured"]["outcome"], "dropped")
        self.assertEqual(record["unmeasured"]["land_slot"], "U_NOT_APPLICABLE")
        self.assertIsNone(record["measured"]["total_execution_cost_lamports"])

    def test_an_expired_attempt_records_the_slot_it_could_no_longer_land_after(self):
        record = _record("expired")
        self.assertEqual(record["measured"]["outcome"], "expired")
        self.assertIsNotNone(record["measured"]["expiry_slot"])
        self.assertIsNotNone(record["measured"]["blockhash_slot"])

    def test_no_fault_record_defaults_an_unknown_to_zero(self):
        for fault in B18B.FAULTS:
            record = _record(fault)
            for field, value in record["measured"].items():
                if value == 0 and field not in ("attempt_index", "jito_tip_lamports"):
                    self.fail(f"{fault}: {field} is 0; a zero must be measured, never a default")


# ----------------------------------------------------------------------------------------------
# A fault record can never pass as evidence
# ----------------------------------------------------------------------------------------------

class FaultRecordsAreNotEvidenceTests(unittest.TestCase):

    def test_every_fault_record_says_it_is_not_evidence(self):
        for fault in B18B.FAULTS:
            with self.subTest(fault=fault):
                record = _record(fault)
                self.assertEqual(record["stage"], "rehearsal")
                self.assertIn("INJECTED FAULT", record["record_is_not_evidence"])
                self.assertIs(record["executable"], False)
                self.assertEqual(record["synthetic_fault"]["fault"], fault)

    def test_a_rehearsal_record_without_its_fault_block_is_refused(self):
        record = _record("dropped")
        del record["synthetic_fault"]
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("name the synthetic fault", str(refusal.exception))

    def test_a_rehearsal_record_that_drops_the_not_evidence_marker_is_refused(self):
        record = _record("dropped")
        del record["record_is_not_evidence"]
        with self.assertRaises(B18A.RecordRefused) as refusal:
            B18A.assert_conforms(record)
        self.assertIn("not evidence", str(refusal.exception))

    def test_a_rehearsal_record_may_not_be_marked_executable(self):
        record = _record("dropped")
        record["executable"] = True
        with self.assertRaises(B18A.RecordRefused):
            B18A.assert_conforms(record)

    def test_a_failure_outcome_may_not_be_relabelled_as_a_shadow_record(self):
        """The reason these are a fourth stage: shadow may not claim an outcome it could not have."""
        record = _record("failed_on_chain")
        record["stage"] = "shadow"
        with self.assertRaises(B18A.RecordRefused):
            B18A.assert_conforms(record)

    def test_landed_is_not_reachable_without_a_real_send(self):
        """If this ever starts passing, something in this repository sent a transaction."""
        report = B18B.rehearse_all()
        self.assertEqual(report["outcome_enum_coverage"]["unreachable_without_a_real_send"],
                         ["landed"])
        self.assertNotIn("landed", report["outcome_enum_coverage"]["reached"])

    def test_the_sweep_reaches_every_other_frozen_outcome(self):
        """The harness's purpose, stated as a test rather than as a claim in a handoff."""
        report = B18B.rehearse_all()
        expected = sorted(set(B18A.OUTCOMES) - {"landed"})
        self.assertEqual(report["outcome_enum_coverage"]["reached"], expected)

    def test_the_sweep_reaches_the_reason_codes_only_failure_produces(self):
        report = B18B.rehearse_all()
        for code in ("U_PROVIDER_SILENT", "U_LOST"):
            self.assertIn(code, report["reason_codes_exercised"])


# ----------------------------------------------------------------------------------------------
# Clocks
# ----------------------------------------------------------------------------------------------

class ClockCoherenceTests(unittest.TestCase):

    def test_a_coherent_chain_is_accepted(self):
        self.assertTrue(B18B.assert_clock_coherent(_chain("provider_503")))

    def test_a_decision_may_not_precede_the_observation_it_rests_on(self):
        record = _record("dropped")
        record["measured"]["decision_unix_nanos"] = \
            record["measured"]["observation_unix_nanos"] - 1
        with self.assertRaises(B18B.RecordRefused) as refusal:
            B18B.assert_clock_coherent([record])
        self.assertIn("precedes the observation", str(refusal.exception))

    def test_a_receipt_may_not_precede_its_send(self):
        record = _record("dropped")
        record["measured"]["receipt_unix_nanos"] = record["measured"]["send_unix_nanos"] - 1
        with self.assertRaises(B18B.RecordRefused) as refusal:
            B18B.assert_clock_coherent([record])
        self.assertIn("precedes", str(refusal.exception))

    def test_a_finalize_may_not_precede_its_landing(self):
        record = _record("failed_on_chain")
        record["measured"]["finalize_unix_nanos"] = record["measured"]["land_unix_nanos"] - 1
        with self.assertRaises(B18B.RecordRefused):
            B18B.assert_clock_coherent([record])

    def test_a_stepped_wall_clock_is_caught_rather_than_stored(self):
        """Slots forward and wall clock backward is a stepped clock, not reordered evidence."""
        first = B18B.fault_record("dropped", B18B.synthetic_observation(0), ENDPOINT,
                                  clock_source=CLOCK)
        second = B18B.fault_record("dropped", B18B.synthetic_observation(1), ENDPOINT,
                                   clock_source=CLOCK)
        second["measured"]["observation_unix_nanos"] = \
            first["measured"]["observation_unix_nanos"] - 1_000
        second["measured"]["decision_unix_nanos"] = \
            second["measured"]["observation_unix_nanos"] + 1
        with self.assertRaises(B18B.RecordRefused) as refusal:
            B18B.assert_clock_coherent([first, second])
        self.assertIn("stepped backwards", str(refusal.exception))

    def test_every_record_declares_which_clock_produced_it(self):
        record = _record("dropped")
        self.assertIn("NOT monotonic", record["measured"]["clock_source"])


# ----------------------------------------------------------------------------------------------
# Durability, kill and resume, quarantine
# ----------------------------------------------------------------------------------------------

class DurabilityTests(unittest.TestCase):

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = pathlib.Path(self._directory.name)

    def test_a_written_file_round_trips(self):
        chain = _chain("provider_503")
        path = B18B.write_records_durably(self.root / "r.json", chain)
        self.assertEqual(len(B18B.read_records(path)), len(chain))

    def test_the_write_leaves_no_partial_file_behind(self):
        """Write-then-rename, so a reader never sees a half-written record file."""
        B18B.write_records_durably(self.root / "r.json", _chain("provider_503"))
        self.assertEqual(list(self.root.glob("*.partial")), [])

    def test_the_destination_never_appears_unless_the_rename_completes(self):
        """The atomicity itself, not merely the absence of a leftover temporary.

        Checking only for a stray `.partial` passed with the rename removed entirely, because a
        direct write never creates one -- a mutation caught it. Failing the rename must leave the
        destination ABSENT; a direct write would leave it there, complete, having never renamed.
        """
        original = pathlib.Path.replace

        def refuse(self, target):
            raise OSError("simulated crash between write and rename")

        pathlib.Path.replace = refuse
        self.addCleanup(setattr, pathlib.Path, "replace", original)
        destination = self.root / "r.json"
        with self.assertRaises(OSError):
            B18B.write_records_durably(destination, _chain("provider_503"))
        self.assertFalse(destination.exists(),
                         "the destination exists although the rename never completed, so the "
                         "write was not atomic")

    def test_a_truncated_file_is_refused_rather_than_parsed_as_a_shorter_run(self):
        """The missing attempts would look like attempts that never happened."""
        path = B18B.write_records_durably(self.root / "r.json", _chain("provider_503"))
        text = path.read_text()
        path.write_text(text[:len(text) // 2])
        with self.assertRaises(B18B.RecordRefused) as refusal:
            B18B.read_records(path)
        self.assertIn("absence", str(refusal.exception))

    def test_a_file_whose_count_disagrees_with_its_contents_is_refused(self):
        path = B18B.write_records_durably(self.root / "r.json", _chain("provider_503"))
        document = json.loads(path.read_text())
        document["records"].pop()
        path.write_text(json.dumps(document))
        with self.assertRaises(B18B.RecordRefused) as refusal:
            B18B.read_records(path)
        self.assertIn("says it holds", str(refusal.exception))

    def test_a_file_that_disagrees_with_its_own_digest_is_refused(self):
        path = B18B.write_records_durably(self.root / "r.json", _chain("provider_503"))
        document = json.loads(path.read_text())
        document["records"][0]["record_sha256"] = "0" * 64
        path.write_text(json.dumps(document))
        with self.assertRaises(B18B.RecordRefused) as refusal:
            B18B.read_records(path)
        self.assertIn("digest", str(refusal.exception))


class KillResumeAndQuarantineTests(unittest.TestCase):

    def test_a_resumed_run_reports_what_the_kill_lost(self):
        chain = _chain("provider_503")
        survived = [chain[0], chain[2]]           # attempt 1 died with the process
        resumed = B18B.resume_after_kill(survived, all_intended=3)
        self.assertEqual(resumed["attempts_lost_to_the_kill"], [1])
        self.assertEqual(resumed["reason_code"], "U_LOST")

    def test_a_resumed_run_does_not_renumber_the_survivors_to_look_contiguous(self):
        chain = _chain("provider_503")
        resumed = B18B.resume_after_kill([chain[0], chain[2]], all_intended=3)
        self.assertEqual(resumed["attempts_durably_written"], [0, 2])

    def test_a_resumed_run_does_not_reconstruct_the_lost_attempts(self):
        """A fabricated attempt is indistinguishable from a real one, which is why it must not exist."""
        resumed = B18B.resume_after_kill([_chain("provider_503")[0]], all_intended=3)
        self.assertEqual(resumed["attempts_lost_to_the_kill"], [1, 2])
        self.assertIn("not_reconstructed", resumed)

    def test_a_clean_run_reports_nothing_lost(self):
        chain = _chain("provider_503")
        resumed = B18B.resume_after_kill(chain, all_intended=3)
        self.assertEqual(resumed["attempts_lost_to_the_kill"], [])
        self.assertIsNone(resumed["reason_code"])

    def test_a_quarantine_marks_the_run_unusable_rather_than_partial(self):
        marker = B18B.quarantine("provider identity changed mid-run", _chain("provider_503"))
        self.assertTrue(marker["quarantined"])
        self.assertIn("INVALIDATED", marker["not_for_use"])
        self.assertIn("may not be reused", marker["not_for_use"])


# ----------------------------------------------------------------------------------------------
# The documented recorder observation
# ----------------------------------------------------------------------------------------------

class RecorderZeroFrameFindingTests(unittest.TestCase):

    def test_the_finding_is_demonstrated_not_asserted(self):
        finding = B18B.recorder_zero_frame_finding()
        self.assertEqual(finding["crc32c_of_empty_body"], 0)
        self.assertGreater(finding["records_the_recorder_counts_as_valid"], 0)
        self.assertTrue(finding["b18a_refuses_them"])

    def test_the_recorder_is_not_changed_by_running_the_finding(self):
        before = (ROOT / "scripts" / "recorder.py").read_bytes()
        B18B.recorder_zero_frame_finding()
        self.assertEqual((ROOT / "scripts" / "recorder.py").read_bytes(), before)

    def test_the_probe_leaves_no_file_behind(self):
        B18B.recorder_zero_frame_finding()
        self.assertFalse((ROOT / ".b18b_zero_probe.seg").exists())

    def test_the_finding_says_why_a_fix_is_not_obviously_safe(self):
        """A finding that only says 'this is wrong' invites an unsafe fix."""
        finding = B18B.recorder_zero_frame_finding()
        self.assertIn("sidecars", finding["what_a_fix_would_need"])
        self.assertIn("untouched", finding["recorder_not_changed"])


# ----------------------------------------------------------------------------------------------
# Safety and determinism of the sweep itself
# ----------------------------------------------------------------------------------------------

class SweepSafetyTests(unittest.TestCase):

    def test_the_sweep_opens_no_socket(self):
        opened = []
        original = socket.socket
        socket.socket = lambda *a, **k: opened.append(1) or original(*a, **k)
        self.addCleanup(setattr, socket, "socket", original)
        B18B.rehearse_all()
        self.assertEqual(opened, [])

    def test_the_closure_has_no_execution_surface(self):
        report = B18B.rehearse_all()
        self.assertEqual(report["no_execution_surface"]["execution_surface_found"], {})
        self.assertIn("not a repository-wide", report["no_execution_surface"]["scope"])

    def test_the_sweep_is_deterministic(self):
        first = json.dumps(B18B.rehearse_all(), sort_keys=True)
        second = json.dumps(B18B.rehearse_all(), sort_keys=True)
        self.assertEqual(first, second)

    def test_no_float_appears_anywhere_in_the_sweep(self):
        def walk(value, path="report"):
            self.assertNotIsInstance(value, float, f"a float reached {path}")
            if isinstance(value, dict):
                for key, item in value.items():
                    walk(item, f"{path}.{key}")
            if isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]")
        walk(B18B.rehearse_all())

    def test_every_record_in_the_sweep_conforms(self):
        report = B18B.rehearse_all()
        for fault, chain in report["chains"].items():
            for record in chain:
                with self.subTest(fault=fault, attempt=record["measured"]["attempt_index"]):
                    self.assertTrue(B18A.assert_conforms(record))

    def test_the_sweep_never_claims_to_be_evaluation_or_execution(self):
        report = B18B.rehearse_all()
        self.assertIs(report["executable"], False)
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertIn("INJECTED FAULT", report["record_is_not_evidence"])

    def test_an_unknown_fault_name_is_refused(self):
        with self.assertRaises(B18B.RecordRefused):
            _record("provider_418")

    def test_the_fault_table_covers_every_mode_the_brief_named(self):
        """A coverage claim belongs in a test, not only in a handoff."""
        for fault in ("provider_403", "provider_429", "provider_503", "dns_failure",
                      "provider_silence", "lost_response", "dropped", "expired",
                      "failed_on_chain"):
            self.assertIn(fault, B18B.FAULTS)


if __name__ == "__main__":
    unittest.main()
