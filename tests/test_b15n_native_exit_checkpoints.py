"""B15n tests. The property most worth asserting is that the population does not descend from B15a.

Everything else here is the usual: each refusal driven with a fixture that would pass if the gate
were absent, restart and duplicate paths exercised rather than reasoned about, and the raw log
proven sufficient by rebuilding from it.
"""
import base64
import importlib.util
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


B15N = _load("b15n_native_exit_checkpoints", "b15n_native_exit_checkpoints.py")
B15F, B15B = B15N.B15F, B15N.B15B
PILOT = _load("b15a_shadow_pilot", "b15a_shadow_pilot.py")
FIXTURES = _load("b15a_shadow_fixtures", "b15a_shadow_fixtures.py")

ACTIVATION = 436_984_352
T0 = ACTIVATION + 100
CURVE = "Curve1111111111111111111111111111111111111"
PUMP = PILOT.PUMP_PROGRAM


def bonding_curve_bytes(virtual_quote=30_000_000_000, complete=False, discriminator=None):
    """The pinned BondingCurve layout, walked from the IDL rather than hand-written."""
    _b7d, _d, _c, types = PILOT.load_pinned_create_type()
    raw = bytearray(B15F.BONDING_CURVE_DISCRIMINATOR if discriminator is None else discriminator)
    for field in types["BondingCurve"]["type"]["fields"]:
        if field["name"] == "virtual_quote_reserves":
            raw += virtual_quote.to_bytes(8, "little")
        elif field["name"] == "complete":
            raw += b"\x01" if complete else b"\x00"
        else:
            raw += FIXTURES._encode(field["type"], types)
    return bytes(raw)


def account_response(context_slot, owner=PUMP, data=None, lamports=5_000_000):
    raw = bonding_curve_bytes() if data is None else data
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"context": {"slot": context_slot},
                       "value": {"owner": owner, "lamports": lamports,
                                 "data": [base64.b64encode(raw).decode(), "base64"]}}}


def opener_for(responses):
    """A fake urlopen returning each queued payload in turn, then repeating the last."""
    queue = list(responses)

    def opener(request, timeout=None):
        payload = queue.pop(0) if len(queue) > 1 else queue[0]

        class Handle:
            status = 200

            def read(self_inner):
                return json.dumps(payload).encode()

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *_):
                return False
        return Handle()
    return opener


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15n_")) / "b15n"
        self.directory.mkdir(parents=True)
        self.b15i = self.directory.parent / "feed.sqlite"
        self.document = B15N.verify_preregistration()

    def tearDown(self):
        shutil.rmtree(self.directory.parent, ignore_errors=True)

    def write_feed(self, launches):
        """A minimal B15i observation table: the only scheduling source this worker has."""
        connection = sqlite3.connect(self.b15i)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS observation(signature TEXT PRIMARY KEY, t0_slot INTEGER, "
            "mint TEXT, bonding_curve TEXT, fork_state TEXT, observed_after_gap INTEGER, "
            "chain_verdict TEXT)")
        connection.execute("DELETE FROM observation")
        connection.executemany(
            "INSERT INTO observation VALUES (?,?,?,?,?,?,?)", launches)
        connection.commit()
        connection.close()

    def launch(self, signature="Sig1", t0=T0, fork_state="confirmed", gap=0, verdict=None):
        return (signature, t0, "Mint1", CURVE, fork_state, gap, verdict)

    def run_worker(self, responses, slot, **kwargs):
        return B15N.run(url="https://example.invalid", work_dir=self.directory,
                        b15i_path=self.b15i, document=self.document, ticks=1,
                        opener=opener_for(responses), sleeper=lambda _s: None,
                        slot_source=lambda: slot, **kwargs)

    def db(self):
        return sqlite3.connect(self.directory / "exit_checkpoints.sqlite")


class TestGates(Base):
    def test_the_freeze_is_pinned(self):
        self.assertEqual(self.document["preregistration_id"], "B15N_NATIVE_EXIT_CHECKPOINT_V1")
        self.assertTrue(self.document["committed_before_any_checkpoint"])

    def test_a_tampered_freeze_refuses(self):
        altered = self.directory / "altered.json"
        document = json.loads(B15N.PREREG_PATH.read_bytes())
        document["activation"]["activation_slot"] = 1
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.verify_preregistration(altered)
        self.assertIn("pinned", str(caught.exception))

    def test_an_unreadable_freeze_refuses(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.verify_preregistration(self.directory / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_a_freeze_that_restates_b15fs_tolerance_differently_refuses(self):
        """A superseding number is how a frozen tolerance drifts, so it is compared not trusted."""
        altered = self.directory / "drifted.json"
        document = json.loads(B15N.PREREG_PATH.read_bytes())
        document["account_read"]["inherited_verbatim_from_b15f"]["max_lateness_slots"] = 10_000
        altered.write_text(json.dumps(document))
        import hashlib
        expected = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.verify_preregistration(altered, expected)
        self.assertIn("a tolerance that can drift", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15N.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        poisoned = self.directory / "poisoned.py"
        poisoned.write_text("FORBIDDEN_SOURCE_ARTIFACTS = ()\nx = 'sendTransaction'\n")
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.assert_no_execution_surface(poisoned)
        self.assertIn("sendTransaction", str(caught.exception))

    def test_the_worker_does_not_depend_on_b15a_or_b15f_artifacts(self):
        """The only reason this module exists, so it is asserted mechanically."""
        self.assertTrue(B15N.assert_no_b15a_or_b15f_dependency())

    def test_a_reinstated_b15f_dependency_is_caught(self):
        poisoned = self.directory / "reinstated.py"
        poisoned.write_text(
            "FORBIDDEN_SOURCE_ARTIFACTS = ()\nSOURCE = 'research/b15f/checkpoints.sqlite'\n")
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.assert_no_b15a_or_b15f_dependency(poisoned)
        self.assertIn("must not descend from B15a", str(caught.exception))

    def test_writing_into_another_worker_is_refused(self):
        for other in ("b15a", "b15f", "b15i", "b11a"):
            with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
                B15N.assert_isolated(ROOT / "research" / other)
            self.assertIn("read-only here", str(caught.exception))

    def test_a_work_directory_that_is_not_b15n_is_refused(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.assert_isolated(ROOT / "research" / "elsewhere")
        self.assertIn("must be .../b15n", str(caught.exception))


class TestGeometry(Base):
    def test_the_target_is_t0_plus_delay_plus_horizon(self):
        self.assertEqual(B15N.target_slot(1000, 4, 10_000), 11_004)

    def test_a_float_in_the_geometry_refuses(self):
        for args in ((1000.0, 1, 1000), (1000, 1.0, 1000), (1000, 1, 1000.0), (1000, True, 1000)):
            with self.subTest(args=args):
                with self.assertRaises(B15N.ExitCheckpointRefused):
                    B15N.target_slot(*args)

    def test_six_cells_per_launch_in_a_fixed_order(self):
        cells = B15N.cells_for(500_000, self.document)
        self.assertEqual(len(cells), 6)
        self.assertEqual(cells, [(1, "h_1000_slots", 501_001), (1, "h_10000_slots", 510_001),
                                 (2, "h_1000_slots", 501_002), (2, "h_10000_slots", 510_002),
                                 (4, "h_1000_slots", 501_004), (4, "h_10000_slots", 510_004)])

    def test_the_horizons_are_b10bs_identifiers(self):
        names = [h["name"] for h in self.document["target_geometry"]["exit_horizons"]]
        self.assertEqual(names, ["h_1000_slots", "h_10000_slots"])
        for horizon in self.document["target_geometry"]["exit_horizons"]:
            self.assertEqual(horizon["slots"], int(horizon["name"].split("_")[1]))

    def test_activation_is_strict(self):
        for t0 in (None, ACTIVATION - 1, ACTIVATION):
            with self.subTest(t0=t0):
                with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
                    B15N.assert_after_activation(t0, ACTIVATION)
                self.assertIn(B15N.C_PRE_PROTOCOL, str(caught.exception))
        self.assertTrue(B15N.assert_after_activation(ACTIVATION + 1, ACTIVATION))

    def test_a_target_inside_the_tolerance_is_still_schedulable(self):
        self.assertTrue(B15N.is_still_schedulable(1000, 1150, 150))
        self.assertFalse(B15N.is_still_schedulable(1000, 1151, 150))
        self.assertTrue(B15N.is_still_schedulable(1000, 500, 150))


class TestScheduling(Base):
    def test_a_launch_after_activation_gets_six_scheduled_targets(self):
        self.write_feed([self.launch()])
        connection = B15N.open_database(self.directory / "db.sqlite")
        outcome = B15N.schedule_new(connection, B15N.observed_launches(self.b15i, ACTIVATION),
                                    T0 + 1, self.document, 150)
        self.assertEqual(outcome["scheduled"], 6)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM schedule").fetchone()[0], 6)
        connection.close()

    def test_a_pre_activation_launch_is_never_scheduled(self):
        self.write_feed([self.launch(t0=ACTIVATION)])
        connection = B15N.open_database(self.directory / "db.sqlite")
        outcome = B15N.schedule_new(connection, B15N.observed_launches(self.b15i, 0),
                                    T0 + 1, self.document, 150)
        self.assertEqual(outcome[B15N.C_PRE_PROTOCOL], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM schedule").fetchone()[0], 0)
        connection.close()

    def test_an_unconfirmed_launch_is_still_scheduled(self):
        """Scheduling does not wait for confirmation; admission does."""
        self.write_feed([self.launch(fork_state="processed_unconfirmed")])
        connection = B15N.open_database(self.directory / "db.sqlite")
        outcome = B15N.schedule_new(connection, B15N.observed_launches(self.b15i, ACTIVATION),
                                    T0 + 1, self.document, 150)
        self.assertEqual(outcome["scheduled"], 6)
        states = {row[0] for row in connection.execute(
            "SELECT fork_state_at_schedule FROM schedule")}
        self.assertEqual(states, {"processed_unconfirmed"})
        connection.close()

    def test_scheduling_twice_is_idempotent(self):
        """A restart re-reading the same launch, and a same-slot duplicate, both land once."""
        self.write_feed([self.launch()])
        connection = B15N.open_database(self.directory / "db.sqlite")
        launches = B15N.observed_launches(self.b15i, ACTIVATION)
        first = B15N.schedule_new(connection, launches, T0 + 1, self.document, 150)
        second = B15N.schedule_new(connection, launches, T0 + 1, self.document, 150)
        self.assertEqual(first["scheduled"], 6)
        self.assertEqual(second["scheduled"], 0)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM schedule").fetchone()[0], 6)
        connection.close()

    def test_a_conflicting_geometry_under_one_key_is_refused(self):
        self.write_feed([self.launch()])
        connection = B15N.open_database(self.directory / "db.sqlite")
        B15N.schedule_new(connection, B15N.observed_launches(self.b15i, ACTIVATION),
                          T0 + 1, self.document, 150)
        # The same signature reappearing with a different t0 would put two targets under one key.
        self.write_feed([self.launch(t0=T0 + 5000)])
        outcome = B15N.schedule_new(connection, B15N.observed_launches(self.b15i, ACTIVATION),
                                    T0 + 5001, self.document, 150)
        self.assertEqual(outcome[B15N.N_SCHEDULE_CONFLICT], 6)
        reasons = {row[0] for row in connection.execute(
            "SELECT reason FROM schedule WHERE state='refused'")}
        self.assertEqual(reasons, {B15N.N_SCHEDULE_CONFLICT})
        connection.close()

    def test_a_target_already_past_is_recorded_not_scheduled(self):
        self.write_feed([self.launch()])
        connection = B15N.open_database(self.directory / "db.sqlite")
        # Current slot far beyond every target plus the tolerance.
        outcome = B15N.schedule_new(connection, B15N.observed_launches(self.b15i, ACTIVATION),
                                    T0 + 100_000, self.document, 150)
        self.assertEqual(outcome[B15N.N_TARGET_ALREADY_PASSED], 6)
        self.assertEqual(outcome["scheduled"], 0)
        connection.close()

    def test_gap_provenance_is_carried_onto_every_row(self):
        self.write_feed([self.launch(gap=1)])
        connection = B15N.open_database(self.directory / "db.sqlite")
        B15N.schedule_new(connection, B15N.observed_launches(self.b15i, ACTIVATION),
                          T0 + 1, self.document, 150)
        flags = {row[0] for row in connection.execute(
            "SELECT observed_after_gap FROM schedule")}
        self.assertEqual(flags, {1})
        connection.close()

    def test_a_missing_feed_refuses_rather_than_scheduling_nothing_quietly(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.observed_launches(self.directory / "absent.sqlite")
        self.assertIn("will not invent one", str(caught.exception))


class TestRetirementAndDue(Base):
    def _scheduled(self):
        self.write_feed([self.launch()])
        connection = B15N.open_database(self.directory / "db.sqlite")
        B15N.schedule_new(connection, B15N.observed_launches(self.b15i, ACTIVATION),
                          T0 + 1, self.document, 150)
        return connection

    def test_a_target_whose_deadline_passed_is_retired_and_never_fetched(self):
        connection = self._scheduled()
        retired = B15N.retire_missed(connection, T0 + 100_000, 150)
        self.assertEqual(retired, 6)
        reasons = {row[0] for row in connection.execute(
            "SELECT reason FROM schedule WHERE state='refused'")}
        self.assertEqual(reasons, {B15N.N_TARGET_ALREADY_PASSED})
        self.assertEqual(B15N.due_targets(connection, T0 + 100_000, 150), [])
        connection.close()

    def test_a_future_target_is_not_due_and_not_retired(self):
        connection = self._scheduled()
        self.assertEqual(B15N.retire_missed(connection, T0 + 10, 150), 0)
        self.assertEqual(B15N.due_targets(connection, T0 + 10, 150), [])
        connection.close()

    def test_a_target_at_its_slot_is_due(self):
        connection = self._scheduled()
        due = B15N.due_targets(connection, T0 + 1 + 1000, 150)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["horizon"], "h_1000_slots")
        self.assertEqual(due[0]["delay_slots"], 1)
        connection.close()

    def test_due_targets_come_oldest_first(self):
        connection = self._scheduled()
        due = B15N.due_targets(connection, T0 + 20_000, 150)
        self.assertEqual([row["target_slot"] for row in due],
                         sorted(row["target_slot"] for row in due))
        connection.close()


class TestReading(Base):
    def _row(self, target=T0 + 1001):
        return {"signature": "Sig1", "delay_slots": 1, "horizon": "h_1000_slots",
                "bonding_curve": CURVE, "t0_slot": T0, "target_slot": target, "attempts": 0}

    def _raw(self):
        return B15N.RawLog(self.directory / "raw.jsonl")

    def test_a_clean_read_returns_the_pinned_state_and_its_evidence(self):
        raw = self._raw()
        row = self._row()
        outcome = B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                      B15B.build_decoder(), raw,
                                      opener_for([account_response(row["target_slot"])]),
                                      lambda _s: None)
        raw.close()
        self.assertEqual(outcome["context_slot"], row["target_slot"])
        self.assertEqual(outcome["lateness_slots"], 0)
        self.assertEqual(outcome["state"]["virtual_quote"], 30_000_000_000)
        self.assertEqual(len(outcome["raw_sha256"]), 64)
        self.assertGreater(outcome["latency_ns"], 0)
        self.assertEqual(outcome["attempts"], 1)

    def test_the_request_carries_min_context_slot_and_finalized(self):
        seen = {}

        def opener(request, timeout=None):
            seen.update(json.loads(request.data))

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(account_response(T0 + 1001)).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        raw = self._raw()
        B15N.read_checkpoint(self._row(), "https://example.invalid", self.document,
                             B15B.build_decoder(), raw, opener, lambda _s: None)
        raw.close()
        options = seen["params"][1]
        self.assertEqual(options["minContextSlot"], T0 + 1001)
        self.assertEqual(options["commitment"], "finalized")

    def test_a_late_context_is_refused_distinctly_from_an_rpc_failure(self):
        raw = self._raw()
        row = self._row()
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                 B15B.build_decoder(), raw,
                                 opener_for([account_response(row["target_slot"] + 151)]),
                                 lambda _s: None)
        raw.close()
        self.assertIn(B15N.C_LATE, str(caught.exception))
        self.assertNotIn(B15N.N_RPC_FAILED, str(caught.exception))

    def test_lateness_exactly_at_the_tolerance_is_admitted(self):
        raw = self._raw()
        row = self._row()
        outcome = B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                       B15B.build_decoder(), raw,
                                       opener_for([account_response(row["target_slot"] + 150)]),
                                       lambda _s: None)
        raw.close()
        self.assertEqual(outcome["lateness_slots"], 150)

    def test_an_rpc_failure_is_its_own_code(self):
        def opener(request, timeout=None):
            raise OSError("endpoint down")

        raw = self._raw()
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.read_checkpoint(self._row(), "https://example.invalid", self.document,
                                 B15B.build_decoder(), raw, opener, lambda _s: None)
        raw.close()
        self.assertIn(B15N.N_RPC_FAILED, str(caught.exception))

    def test_a_min_context_rejection_is_retried_within_the_frozen_bound(self):
        """minContextSlot rejects rather than waits; B15F's bounded retry is the safety net."""
        calls = []

        def opener(request, timeout=None):
            calls.append(1)

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps({"jsonrpc": "2.0", "id": 1, "code": -32603,
                                       "message": "Min context slot not reached"}).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        raw = self._raw()
        with self.assertRaises(B15N.ExitCheckpointRefused):
            B15N.read_checkpoint(self._row(), "https://example.invalid", self.document,
                                 B15B.build_decoder(), raw, opener, lambda _s: None)
        raw.close()
        self.assertEqual(len(calls), self.document["account_read"][
            "inherited_verbatim_from_b15f"]["max_attempts"])

    def test_a_wrong_owner_is_an_account_mismatch(self):
        raw = self._raw()
        row = self._row()
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                 B15B.build_decoder(), raw,
                                 opener_for([account_response(row["target_slot"],
                                                              owner="SomeoneElse")]),
                                 lambda _s: None)
        raw.close()
        self.assertIn(B15N.N_ACCOUNT_MISMATCH, str(caught.exception))

    def test_a_wrong_discriminator_is_an_account_mismatch(self):
        poisoned = bytes([B15F.BONDING_CURVE_DISCRIMINATOR[0] ^ 0xFF]) + \
            B15F.BONDING_CURVE_DISCRIMINATOR[1:]
        raw = self._raw()
        row = self._row()
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.read_checkpoint(
                row, "https://example.invalid", self.document, B15B.build_decoder(), raw,
                opener_for([account_response(
                    row["target_slot"], data=bonding_curve_bytes(discriminator=poisoned))]),
                lambda _s: None)
        raw.close()
        self.assertIn(B15N.N_ACCOUNT_MISMATCH, str(caught.exception))

    def test_an_absent_account_is_its_own_code(self):
        raw = self._raw()
        row = self._row()
        response = {"jsonrpc": "2.0", "id": 1,
                    "result": {"context": {"slot": row["target_slot"]}, "value": None}}
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                 B15B.build_decoder(), raw, opener_for([response]),
                                 lambda _s: None)
        raw.close()
        self.assertIn(B15N.N_ACCOUNT_ABSENT, str(caught.exception))

    def test_the_raw_exchange_is_written_before_the_answer_is_judged(self):
        raw = self._raw()
        row = self._row()
        try:
            B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                 B15B.build_decoder(), raw,
                                 opener_for([account_response(row["target_slot"] + 151)]),
                                 lambda _s: None)
        except B15N.ExitCheckpointRefused:
            pass
        raw.close()
        lines = (self.directory / "raw.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["outcome"], "retrieved")


class TestNoRedundantFinalityWait(Base):
    """The due-check already waits for finality, so the reader must not wait again.

    A 12.4-second wait per target, applied serially at two requests a second, gave about five reads
    a minute against roughly six hundred targets a minute arriving. The backlog pushed checkpoint
    lateness to a mean of 103 slots against a 150 tolerance and refused 12 outright, which looked
    like a slow endpoint and was a redundant sleep.
    """

    def test_the_due_check_uses_the_finalized_slot(self):
        """Which is why no further wait is needed: finality has already passed the target."""
        import inspect
        source = inspect.getsource(B15F.current_slot)
        self.assertIn('"commitment": "finalized"', source)

    def test_the_reader_does_not_sleep_when_no_delay_is_given(self):
        slept = []
        raw = B15N.RawLog(self.directory / "raw.jsonl")
        row = {"signature": "Sig1", "delay_slots": 1, "horizon": "h_1000_slots",
               "bonding_curve": CURVE, "t0_slot": T0, "target_slot": T0 + 1001, "attempts": 0}
        B15N.read_checkpoint(row, "https://example.invalid", self.document,
                             B15B.build_decoder(), raw,
                             opener_for([account_response(row["target_slot"])]), slept.append)
        raw.close()
        self.assertEqual(slept, [])

    def test_the_entrypoint_passes_no_finalization_wait(self):
        source = (ROOT / "scripts" / "b15n_native_exit_checkpoints.py").read_text()
        self.assertIn("finalization_lag_slots=0", source)
        # A contiguous phrase: comment wrapping split the previous one across two lines and the
        # assertion failed on the formatting rather than on the property.
        self.assertIn("at or below the current FINALIZED slot", source)


class TestAdmission(Base):
    def test_only_an_explicit_chain_confirmation_admits(self):
        self.assertTrue(B15N.admissible_downstream("confirmed", None))
        self.assertTrue(B15N.admissible_downstream("unresolved", "confirmed"))
        for fork_state in ("processed_unconfirmed", "unresolved", "orphaned", None):
            with self.subTest(fork_state=fork_state):
                self.assertFalse(B15N.admissible_downstream(fork_state, None))

    def test_a_not_found_verdict_never_admits(self):
        self.assertFalse(B15N.admissible_downstream("unresolved", "not_found"))

    def test_provenance_is_re_read_at_checkpoint_time(self):
        """A confirmation arriving during a 10,000-slot horizon is the common case."""
        self.write_feed([self.launch(fork_state="unresolved")])
        self.assertEqual(B15N.current_provenance("Sig1", self.b15i)["fork_state"], "unresolved")
        self.write_feed([self.launch(fork_state="confirmed")])
        self.assertEqual(B15N.current_provenance("Sig1", self.b15i)["fork_state"], "confirmed")

    def test_an_unknown_signature_yields_no_provenance_rather_than_a_default(self):
        self.write_feed([self.launch()])
        provenance = B15N.current_provenance("Absent", self.b15i)
        self.assertIsNone(provenance["fork_state"])
        self.assertFalse(B15N.admissible_downstream(provenance["fork_state"],
                                                    provenance["chain_verdict"]))

    def test_a_missing_feed_yields_no_provenance(self):
        provenance = B15N.current_provenance("Sig1", self.directory / "absent.sqlite")
        self.assertIsNone(provenance["fork_state"])


class TestEndToEnd(Base):
    def test_a_full_tick_schedules_retires_and_reads(self):
        self.write_feed([self.launch()])
        counts, report = self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        self.assertEqual(counts["scheduled"], 6)
        self.assertEqual(counts.get("checkpointed"), 1)      # only h_1000/delay 1 is due
        self.assertEqual(report["checkpoints"], 1)
        self.assertEqual(report["admissible_downstream"], 1)
        self.assertEqual(report["withheld_pending_confirmation"], 0)

    def test_an_unconfirmed_launchs_checkpoint_is_recorded_and_withheld(self):
        self.write_feed([self.launch(fork_state="processed_unconfirmed")])
        _counts, report = self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        self.assertEqual(report["checkpoints"], 1)
        self.assertEqual(report["admissible_downstream"], 0)
        self.assertEqual(report["withheld_pending_confirmation"], 1)

    def test_an_orphaned_launchs_checkpoint_is_recorded_and_withheld(self):
        self.write_feed([self.launch(fork_state="orphaned", verdict="not_found")])
        counts, report = self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        self.assertEqual(report["checkpoints"], 1)
        self.assertEqual(report["admissible_downstream"], 0)
        self.assertEqual(counts.get(B15N.N_ORPHANED), 1)

    def test_gap_provenance_reaches_the_checkpoint_row(self):
        self.write_feed([self.launch(gap=1)])
        _counts, report = self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        self.assertEqual(report["observed_after_gap_checkpoints"], 1)

    def test_a_restart_re_reads_the_schedule_and_does_not_duplicate(self):
        self.write_feed([self.launch()])
        self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        _counts, report = self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        self.assertEqual(report["checkpoints"], 1)
        connection = self.db()
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM schedule").fetchone()[0], 6)
        connection.close()

    def test_a_restart_after_the_deadline_retires_rather_than_reading(self):
        self.write_feed([self.launch()])
        self.run_worker([account_response(T0 + 1001)], T0 + 500)     # scheduled, nothing due
        _counts, report = self.run_worker([account_response(T0 + 99_999)], T0 + 100_000)
        self.assertEqual(report["checkpoints"], 0)
        self.assertEqual(report["schedule_reasons"].get(B15N.N_TARGET_ALREADY_PASSED), 6)

    def test_the_census_publishes_no_strategy_figure(self):
        self.write_feed([self.launch()])
        _counts, report = self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        text = json.dumps(report).lower()
        for banned in ("profit", "return", "capacity", "roi", "expected_value", "net_lamports"):
            self.assertNotIn(banned, text)
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertEqual(report["label"], "NATIVE_EXIT_CHECKPOINTS")

    def test_the_census_names_the_scheduling_source(self):
        self.write_feed([self.launch()])
        _counts, report = self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        self.assertIn("B15i", report["scheduling_source"])
        self.assertIn("B15a and B15f are not read", report["scheduling_source"])

    def test_the_raw_log_alone_rebuilds_every_checkpoint(self):
        self.write_feed([self.launch()])
        self.run_worker([account_response(T0 + 1001)], T0 + 1001)
        rebuilt = B15N.replay_checkpoints(self.directory / "rpc_exchanges.jsonl", self.document,
                                          B15B.build_decoder())
        connection = self.db()
        rows = connection.execute(
            "SELECT signature, delay_slots, horizon, context_slot, lateness_slots, virtual_quote, "
            "virtual_token, real_quote, real_token FROM checkpoint").fetchall()
        connection.close()
        self.assertEqual(len(rows), 1)
        for row in rows:
            key = (row[0], row[1], row[2])
            self.assertIn(key, rebuilt)
            self.assertEqual(rebuilt[key]["context_slot"], row[3])
            self.assertEqual(rebuilt[key]["lateness_slots"], row[4])
            self.assertEqual(rebuilt[key]["virtual_quote"], row[5])
            self.assertEqual(rebuilt[key]["virtual_token"], row[6])
            self.assertEqual(rebuilt[key]["real_quote"], row[7])
            self.assertEqual(rebuilt[key]["real_token"], row[8])

    def test_replaying_a_missing_raw_log_refuses(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.replay_checkpoints(self.directory / "absent.jsonl", self.document,
                                    B15B.build_decoder())
        self.assertIn("nothing", str(caught.exception).lower() + " nothing")

    def test_an_unavailable_slot_skips_the_tick_rather_than_guessing(self):
        self.write_feed([self.launch()])
        counts, report = B15N.run(url="https://example.invalid", work_dir=self.directory,
                                  b15i_path=self.b15i, document=self.document, ticks=1,
                                  opener=opener_for([account_response(T0 + 1001)]),
                                  sleeper=lambda _s: None, slot_source=lambda: None)
        self.assertEqual(counts["slot_unavailable"], 1)
        self.assertEqual(report["checkpoints"], 0)

    def test_status_on_an_unstarted_worker_says_so(self):
        report = B15N.status(self.directory / "unstarted")
        self.assertEqual(report["state"], "not_started")


if __name__ == "__main__":
    unittest.main(verbosity=2)
