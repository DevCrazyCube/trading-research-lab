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


def batch_response(context_slot, curves, nulls=(), owner=PUMP, data=None, extra=0, drop=0):
    """A getMultipleAccounts shape: one shared context slot and one element per requested account."""
    raw = bonding_curve_bytes() if data is None else data
    values = []
    for curve in curves:
        if curve in nulls:
            values.append(None)
        else:
            values.append({"owner": owner, "lamports": 5_000_000,
                           "data": [base64.b64encode(raw).decode(), "base64"]})
    for _ in range(extra):
        values.append({"owner": owner, "lamports": 1,
                       "data": [base64.b64encode(raw).decode(), "base64"]})
    if drop:
        values = values[:-drop]
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"context": {"slot": context_slot}, "value": values}}


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
        self.v2 = B15N.verify_preregistration_v2()

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
                        b15i_path=self.b15i, document=self.v2, ticks=1,
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

    def test_no_finalization_wait_parameter_survives_anywhere(self):
        """The parameter is gone entirely, not merely defaulted to zero."""
        source = (ROOT / "scripts" / "b15n_native_exit_checkpoints.py").read_text()
        self.assertNotIn("finalization_lag_slots", source)
        # A contiguous phrase: comment wrapping split an earlier assertion across two lines and it
        # failed on the formatting rather than on the property.
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
        counts, report = self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        self.assertEqual(counts["scheduled"], 6)
        self.assertEqual(counts.get("checkpointed"), 1)      # only h_1000/delay 1 is due
        self.assertEqual(report["checkpoints"], 1)
        self.assertEqual(report["admissible_downstream"], 1)
        self.assertEqual(report["withheld_pending_confirmation"], 0)

    def test_an_unconfirmed_launchs_checkpoint_is_recorded_and_withheld(self):
        self.write_feed([self.launch(fork_state="processed_unconfirmed")])
        _counts, report = self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        self.assertEqual(report["checkpoints"], 1)
        self.assertEqual(report["admissible_downstream"], 0)
        self.assertEqual(report["withheld_pending_confirmation"], 1)

    def test_an_orphaned_launchs_checkpoint_is_recorded_and_withheld(self):
        self.write_feed([self.launch(fork_state="orphaned", verdict="not_found")])
        counts, report = self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        self.assertEqual(report["checkpoints"], 1)
        self.assertEqual(report["admissible_downstream"], 0)
        self.assertEqual(counts.get(B15N.N_ORPHANED), 1)

    def test_gap_provenance_reaches_the_checkpoint_row(self):
        self.write_feed([self.launch(gap=1)])
        _counts, report = self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        self.assertEqual(report["observed_after_gap_checkpoints"], 1)

    def test_a_restart_re_reads_the_schedule_and_does_not_duplicate(self):
        self.write_feed([self.launch()])
        self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        _counts, report = self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        self.assertEqual(report["checkpoints"], 1)
        connection = self.db()
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM schedule").fetchone()[0], 6)
        connection.close()

    def test_a_restart_after_the_deadline_retires_rather_than_reading(self):
        self.write_feed([self.launch()])
        self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 500)     # scheduled, nothing due
        _counts, report = self.run_worker([batch_response(T0 + 99_999, [CURVE])], T0 + 100_000)
        self.assertEqual(report["checkpoints"], 0)
        self.assertEqual(report["schedule_reasons"].get(B15N.N_TARGET_ALREADY_PASSED), 6)

    def test_the_census_publishes_no_strategy_figure(self):
        self.write_feed([self.launch()])
        _counts, report = self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        text = json.dumps(report).lower()
        for banned in ("profit", "return", "capacity", "roi", "expected_value", "net_lamports"):
            self.assertNotIn(banned, text)
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertEqual(report["label"], "NATIVE_EXIT_CHECKPOINTS")

    def test_the_census_names_the_scheduling_source(self):
        self.write_feed([self.launch()])
        _counts, report = self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        self.assertIn("B15i", report["scheduling_source"])
        self.assertIn("B15a and B15f are not read", report["scheduling_source"])

    def test_the_raw_log_alone_rebuilds_every_checkpoint(self):
        self.write_feed([self.launch()])
        self.run_worker([batch_response(T0 + 1001, [CURVE])], T0 + 1001)
        rebuilt = B15N.replay_batched_checkpoints(self.directory / "rpc_exchanges.jsonl",
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
            B15N.replay_batched_checkpoints(self.directory / "absent.jsonl",
                                            B15B.build_decoder())
        self.assertIn("no raw exchange log", str(caught.exception))

    def test_an_unavailable_slot_skips_the_tick_rather_than_guessing(self):
        self.write_feed([self.launch()])
        counts, report = B15N.run(url="https://example.invalid", work_dir=self.directory,
                                  b15i_path=self.b15i, document=self.v2, ticks=1,
                                  opener=opener_for([batch_response(T0 + 1001, [CURVE])]),
                                  sleeper=lambda _s: None, slot_source=lambda: None)
        self.assertEqual(counts["slot_unavailable"], 1)
        self.assertEqual(report["checkpoints"], 0)

    def test_status_on_an_unstarted_worker_says_so(self):
        report = B15N.status(self.directory / "unstarted")
        self.assertEqual(report["state"], "not_started")


class BatchBase(Base):
    def setUp(self):
        super().setUp()
        self.v2 = B15N.verify_preregistration_v2()

    def raw(self):
        return B15N.RawLog(self.directory / "raw.jsonl")

    def rows(self, count=1, curve=None, target=None):
        out = []
        for index in range(count):
            out.append({"signature": f"Sig{index}", "delay_slots": 1, "horizon": "h_1000_slots",
                        "bonding_curve": curve or f"Curve{index}", "t0_slot": T0,
                        "target_slot": (target or T0 + 1001) + index, "attempts": 0})
        return out


class TestV2Freeze(BatchBase):
    def test_the_v2_freeze_is_pinned_and_binds_v1(self):
        self.assertEqual(self.v2["preregistration_id"], "B15N_NATIVE_EXIT_CHECKPOINT_V2")
        self.assertEqual(self.v2["supersedes"], "B15N_NATIVE_EXIT_CHECKPOINT_V1")
        self.assertEqual(self.v2["supersedes_canonical_sha256"], B15N.PREREG_CANONICAL_SHA256)
        self.assertTrue(self.v2["committed_before_transport_change"])

    def test_a_v2_naming_the_wrong_predecessor_refuses(self):
        import hashlib
        altered = self.directory / "v2.json"
        document = json.loads(B15N.PREREG_V2_PATH.read_bytes())
        document["supersedes_canonical_sha256"] = "0" * 64
        altered.write_text(json.dumps(document))
        expected = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.verify_preregistration_v2(altered, expected)
        self.assertIn("must name what it replaces", str(caught.exception))

    def test_a_v2_that_changes_an_inherited_field_refuses(self):
        """The only permitted change is the request method, and that is checked against V1."""
        import hashlib
        for key, value in (("max_lateness_slots", 10_000), ("max_requests_per_second", 50),
                           ("activation_slot", 1), ("entry_delays_slots", [1, 2, 4, 8]),
                           ("max_attempts", 99), ("commitment", "processed")):
            with self.subTest(key=key):
                altered = self.directory / f"v2_{key}.json"
                document = json.loads(B15N.PREREG_V2_PATH.read_bytes())
                document["inherited_verbatim_from_v1"][key] = value
                altered.write_text(json.dumps(document))
                expected = hashlib.sha256(json.dumps(
                    document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
                    B15N.verify_preregistration_v2(altered, expected)
                self.assertIn("the only permitted change is the request method",
                              str(caught.exception))

    def test_an_unreadable_v2_refuses(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.verify_preregistration_v2(self.directory / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_a_tampered_v2_refuses(self):
        altered = self.directory / "v2.json"
        document = json.loads(B15N.PREREG_V2_PATH.read_bytes())
        document["purpose"] = "something else"
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.verify_preregistration_v2(altered)
        self.assertIn("pinned", str(caught.exception))


class TestBatchComposition(BatchBase):
    def test_targets_are_ordered_canonically(self):
        rows = [{"signature": "B", "delay_slots": 1, "horizon": "h_1000_slots",
                 "bonding_curve": "C", "t0_slot": T0, "target_slot": 200, "attempts": 0},
                {"signature": "A", "delay_slots": 4, "horizon": "h_10000_slots",
                 "bonding_curve": "C", "t0_slot": T0, "target_slot": 100, "attempts": 0},
                {"signature": "A", "delay_slots": 2, "horizon": "h_1000_slots",
                 "bonding_curve": "C", "t0_slot": T0, "target_slot": 100, "attempts": 0}]
        ordered = B15N.canonical_order(rows)
        self.assertEqual([(r["target_slot"], r["signature"], r["delay_slots"]) for r in ordered],
                         [(100, "A", 2), (100, "A", 4), (200, "B", 1)])

    def test_the_order_is_stable_under_input_permutation(self):
        rows = self.rows(5)
        import random
        shuffled = list(rows)
        random.Random(7).shuffle(shuffled)
        self.assertEqual(B15N.canonical_order(rows), B15N.canonical_order(shuffled))

    def test_one_curve_serving_many_targets_is_requested_once(self):
        """Six targets of one launch share one bonding curve."""
        rows = [{"signature": "Sig1", "delay_slots": delay, "horizon": horizon,
                 "bonding_curve": CURVE, "t0_slot": T0,
                 "target_slot": T0 + delay + slots, "attempts": 0}
                for delay in (1, 2, 4)
                for horizon, slots in (("h_1000_slots", 1000), ("h_10000_slots", 10_000))]
        curves, served = B15N.batch_targets(rows, 100)
        self.assertEqual(curves, [CURVE])
        self.assertEqual(len(served), 6)

    def test_the_batch_stops_at_the_protocol_limit(self):
        rows = self.rows(150)
        curves, served = B15N.batch_targets(rows, 100)
        self.assertEqual(len(curves), 100)
        self.assertEqual(len(served), 100)
        # And the ones left out are the LATEST targets, so the most at-risk are served first.
        self.assertEqual(curves, [row["bonding_curve"] for row in B15N.canonical_order(rows)][:100])

    def test_a_duplicate_in_the_request_array_is_refused_before_it_is_sent(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.assert_no_duplicate_request(["A", "B", "A"])
        self.assertIn(B15N.N_BATCH_DUPLICATE, str(caught.exception))
        self.assertTrue(B15N.assert_no_duplicate_request(["A", "B"]))

    def test_batch_composition_never_duplicates_a_curve(self):
        rows = self.rows(20, curve=CURVE) + self.rows(5)
        curves, _served = B15N.batch_targets(rows, 100)
        self.assertEqual(len(curves), len(set(curves)))


class TestBatchMapping(BatchBase):
    def test_each_element_maps_to_its_requested_pubkey_by_index(self):
        curves = ["A", "B", "C"]
        elements, context = B15N.map_elements(batch_response(500, curves), curves)
        self.assertEqual(context, 500)
        self.assertEqual(sorted(elements), curves)

    def test_a_length_mismatch_discards_the_whole_batch(self):
        curves = ["A", "B", "C"]
        for kwargs in ({"extra": 1}, {"drop": 1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
                    B15N.map_elements(batch_response(500, curves, **kwargs), curves)
                self.assertIn(B15N.N_BATCH_LENGTH, str(caught.exception))
                self.assertIn("different account", str(caught.exception))

    def test_a_missing_value_array_is_refused(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.map_elements({"result": {"context": {"slot": 5}}}, ["A"])
        self.assertIn(B15N.N_BATCH_LENGTH, str(caught.exception))

    def test_an_absent_or_non_integer_context_is_refused(self):
        for context in (None, "500", 500.0, True):
            with self.subTest(context=context):
                payload = {"result": {"context": {"slot": context}, "value": [None]}}
                with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
                    B15N.map_elements(payload, ["A"])
                self.assertIn(B15N.N_BATCH_CONTEXT, str(caught.exception))

    def test_a_null_element_refuses_only_its_own_curve(self):
        curves = ["A", "B"]
        elements, _context = B15N.map_elements(batch_response(500, curves, nulls=["A"]), curves)
        self.assertIsNone(elements["A"])
        self.assertIsNotNone(elements["B"])

    def test_every_target_must_be_accounted_for(self):
        rows = self.rows(3)
        outcomes = {(rows[0]["signature"], 1, "h_1000_slots"): {"row": rows[0]}}
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.assert_every_target_accounted(rows, outcomes)
        self.assertIn(B15N.N_BATCH_UNACCOUNTED, str(caught.exception))
        self.assertIn("must not hide another", str(caught.exception))

    def test_a_complete_set_of_outcomes_is_accepted(self):
        rows = self.rows(2)
        outcomes = {(row["signature"], row["delay_slots"], row["horizon"]): {"row": row}
                    for row in rows}
        self.assertTrue(B15N.assert_every_target_accounted(rows, outcomes))


class TestBatchRead(BatchBase):
    def test_the_request_carries_min_context_at_the_latest_target(self):
        seen = {}

        def opener(request, timeout=None):
            seen.update(json.loads(request.data))

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(batch_response(
                        T0 + 1010, ["Curve0", "Curve1"])).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        raw = self.raw()
        rows = self.rows(2)
        B15N.fetch_batch(["Curve0", "Curve1"], rows, "https://example.invalid", self.v2, raw,
                         opener, lambda _s: None)
        raw.close()
        self.assertEqual(seen["method"], "getMultipleAccounts")
        self.assertEqual(seen["params"][1]["minContextSlot"],
                         max(row["target_slot"] for row in rows))
        self.assertEqual(seen["params"][1]["commitment"], "finalized")
        self.assertEqual(seen["params"][0], ["Curve0", "Curve1"])

    def test_a_clean_batch_returns_one_outcome_per_target(self):
        raw = self.raw()
        rows = self.rows(3)
        outcomes, served = B15N.read_batch(
            rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
            opener_for([batch_response(T0 + 1003, ["Curve0", "Curve1", "Curve2"])]),
            lambda _s: None)
        raw.close()
        self.assertEqual(len(outcomes), 3)
        self.assertEqual(len(served), 3)
        for outcome in outcomes.values():
            self.assertNotIn("error", outcome)
            self.assertEqual(outcome["state"]["virtual_quote"], 30_000_000_000)

    def test_a_null_element_refuses_that_target_and_not_the_others(self):
        raw = self.raw()
        rows = self.rows(3)
        outcomes, _served = B15N.read_batch(
            rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
            opener_for([batch_response(T0 + 1003, ["Curve0", "Curve1", "Curve2"],
                                       nulls=["Curve1"])]),
            lambda _s: None)
        raw.close()
        errors = {key: outcome.get("error") for key, outcome in outcomes.items()}
        absent = [key for key, error in errors.items() if error]
        self.assertEqual(len(absent), 1)
        self.assertIn(B15N.N_ACCOUNT_ABSENT, errors[absent[0]])
        self.assertEqual(sum(1 for e in errors.values() if not e), 2)

    def test_one_curve_with_several_targets_is_settled_from_one_element(self):
        raw = self.raw()
        rows = [{"signature": "Sig1", "delay_slots": delay, "horizon": "h_1000_slots",
                 "bonding_curve": CURVE, "t0_slot": T0, "target_slot": T0 + 1000 + delay,
                 "attempts": 0} for delay in (1, 2, 4)]
        outcomes, served = B15N.read_batch(
            rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
            opener_for([batch_response(T0 + 1004, [CURVE])]), lambda _s: None)
        raw.close()
        self.assertEqual(len(served), 3)
        self.assertEqual(len(outcomes), 3)
        self.assertEqual({o["request_index"] for o in outcomes.values()}, {0})
        # Each target keeps its OWN lateness against the shared context slot.
        self.assertEqual({o["lateness_slots"] for o in outcomes.values()}, {3, 2, 0})

    def test_a_late_shared_context_refuses_only_the_targets_it_is_late_for(self):
        raw = self.raw()
        rows = [{"signature": "Sig1", "delay_slots": 1, "horizon": "h_1000_slots",
                 "bonding_curve": "Curve0", "t0_slot": T0, "target_slot": T0, "attempts": 0},
                {"signature": "Sig2", "delay_slots": 1, "horizon": "h_1000_slots",
                 "bonding_curve": "Curve1", "t0_slot": T0, "target_slot": T0 + 200,
                 "attempts": 0}]
        outcomes, _served = B15N.read_batch(
            rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
            opener_for([batch_response(T0 + 200, ["Curve0", "Curve1"])]), lambda _s: None)
        raw.close()
        late = [o for o in outcomes.values() if o.get("error")]
        clean = [o for o in outcomes.values() if not o.get("error")]
        self.assertEqual(len(late), 1)
        self.assertIn(B15N.C_LATE, late[0]["error"])
        self.assertEqual(len(clean), 1)

    def test_an_rpc_failure_raises_for_the_whole_batch(self):
        def opener(request, timeout=None):
            raise OSError("endpoint down")

        raw = self.raw()
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.read_batch(self.rows(3), "https://example.invalid", self.v2,
                            B15B.build_decoder(), raw, opener, lambda _s: None)
        raw.close()
        self.assertIn(B15N.N_RPC_FAILED, str(caught.exception))

    def test_a_min_context_rejection_is_retried_within_the_frozen_bound(self):
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

        raw = self.raw()
        with self.assertRaises(B15N.ExitCheckpointRefused):
            B15N.read_batch(self.rows(2), "https://example.invalid", self.v2,
                            B15B.build_decoder(), raw, opener, lambda _s: None)
        raw.close()
        self.assertEqual(len(calls), self.v2["inherited_verbatim_from_v1"]["max_attempts"])

    def test_the_exchange_is_preserved_with_index_evidence_before_judgement(self):
        raw = self.raw()
        rows = self.rows(2)
        try:
            B15N.read_batch(rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
                            opener_for([batch_response(T0 + 1002, ["Curve0", "Curve1"], drop=1)]),
                            lambda _s: None)
        except B15N.ExitCheckpointRefused:
            pass
        raw.close()
        lines = (self.directory / "raw.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["method"], "getMultipleAccounts")
        self.assertEqual([t["request_index"] for t in record["targets"]], [0, 1])
        for target in record["targets"]:
            self.assertEqual(record["bonding_curves"][target["request_index"]],
                             target["bonding_curve"])


class TestRequestReduction(BatchBase):
    def test_one_launchs_six_targets_cost_one_request_instead_of_six(self):
        rows = [{"signature": "Sig1", "delay_slots": delay, "horizon": horizon,
                 "bonding_curve": CURVE, "t0_slot": T0,
                 "target_slot": T0 + delay + slots, "attempts": 0}
                for delay in (1, 2, 4)
                for horizon, slots in (("h_1000_slots", 1000), ("h_10000_slots", 10_000))]
        curves, served = B15N.batch_targets(rows, 100)
        v1_requests = len(rows)
        v2_requests = 1
        self.assertEqual(v1_requests, 6)
        self.assertEqual(len(curves), v2_requests)
        self.assertEqual(len(served), 6)
        self.assertLess(v2_requests, v1_requests)

    def test_a_hundred_distinct_launches_cost_one_request_not_six_hundred(self):
        rows = []
        for index in range(100):
            for delay in (1, 2, 4):
                for horizon, slots in (("h_1000_slots", 1000), ("h_10000_slots", 10_000)):
                    rows.append({"signature": f"Sig{index}", "delay_slots": delay,
                                 "horizon": horizon, "bonding_curve": f"Curve{index}",
                                 "t0_slot": T0, "target_slot": T0 + delay + slots,
                                 "attempts": 0})
        curves, served = B15N.batch_targets(rows, 100)
        self.assertEqual(len(rows), 600)
        self.assertEqual(len(curves), 100)          # one request
        self.assertEqual(len(served), 600)          # serving every target
        self.assertLess(1, len(rows))

    def test_the_reduction_is_reported_by_the_drain(self):
        connection = B15N.open_database(self.directory / "db.sqlite")
        rows = self.rows(3)
        for row in rows:
            connection.execute(
                "INSERT INTO schedule(signature,delay_slots,horizon,mint,bonding_curve,t0_slot,"
                "target_slot,state,reason,attempts,fork_state_at_schedule,observed_after_gap,"
                "scheduled_at_wall_unix,scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["signature"], row["delay_slots"], row["horizon"], "M", row["bonding_curve"],
                 T0, row["target_slot"], B15N.STATE_SCHEDULED, None, 0, "confirmed", 0, 0.0, 0))
        connection.commit()
        raw = self.raw()
        counts = B15N.drain_batched(
            connection, rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw, {},
            opener_for([batch_response(T0 + 1003, ["Curve0", "Curve1", "Curve2"])]),
            lambda _s: None, self.b15i)
        raw.close()
        connection.close()
        self.assertEqual(counts["batched_requests"], 1)
        self.assertEqual(counts["checkpointed"], 3)


class TestV1V2Equivalence(BatchBase):
    """Identical account bytes must decode identically through both transports."""

    def _row(self, target=None):
        return {"signature": "Sig1", "delay_slots": 1, "horizon": "h_1000_slots",
                "bonding_curve": CURVE, "t0_slot": T0,
                "target_slot": target or T0 + 1001, "attempts": 0}

    def test_the_decoded_state_matches_v1_field_for_field(self):
        row = self._row()
        raw_one, raw_two = self.raw(), B15N.RawLog(self.directory / "raw2.jsonl")
        v1 = B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                  B15B.build_decoder(), raw_one,
                                  opener_for([account_response(row["target_slot"])]),
                                  lambda _s: None)
        outcomes, _served = B15N.read_batch(
            [row], "https://example.invalid", self.v2, B15B.build_decoder(), raw_two,
            opener_for([batch_response(row["target_slot"], [CURVE])]), lambda _s: None)
        raw_one.close()
        raw_two.close()
        v2 = outcomes[("Sig1", 1, "h_1000_slots")]
        self.assertEqual(v1["state"], v2["state"])
        self.assertEqual(v1["context_slot"], v2["context_slot"])
        self.assertEqual(v1["lateness_slots"], v2["lateness_slots"])

    def test_the_geometry_decision_matches_v1_at_the_boundary(self):
        for offset, admits in ((0, True), (150, True), (151, False)):
            with self.subTest(offset=offset):
                row = self._row()
                context = row["target_slot"] + offset
                raw_one, raw_two = self.raw(), B15N.RawLog(self.directory / "raw2.jsonl")
                v1_admitted = True
                try:
                    B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                         B15B.build_decoder(), raw_one,
                                         opener_for([account_response(context)]),
                                         lambda _s: None)
                except B15N.ExitCheckpointRefused:
                    v1_admitted = False
                outcomes, _served = B15N.read_batch(
                    [row], "https://example.invalid", self.v2, B15B.build_decoder(), raw_two,
                    opener_for([batch_response(context, [CURVE])]), lambda _s: None)
                raw_one.close()
                raw_two.close()
                v2_admitted = "error" not in outcomes[("Sig1", 1, "h_1000_slots")]
                self.assertEqual(v1_admitted, admits)
                self.assertEqual(v2_admitted, admits)

    def test_a_wrong_discriminator_is_refused_by_both(self):
        poisoned = bytes([B15F.BONDING_CURVE_DISCRIMINATOR[0] ^ 0xFF]) + \
            B15F.BONDING_CURVE_DISCRIMINATOR[1:]
        data = bonding_curve_bytes(discriminator=poisoned)
        row = self._row()
        raw_one, raw_two = self.raw(), B15N.RawLog(self.directory / "raw2.jsonl")
        with self.assertRaises(B15N.ExitCheckpointRefused):
            B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                 B15B.build_decoder(), raw_one,
                                 opener_for([account_response(row["target_slot"], data=data)]),
                                 lambda _s: None)
        outcomes, _served = B15N.read_batch(
            [row], "https://example.invalid", self.v2, B15B.build_decoder(), raw_two,
            opener_for([batch_response(row["target_slot"], [CURVE], data=data)]),
            lambda _s: None)
        raw_one.close()
        raw_two.close()
        self.assertIn(B15N.N_ACCOUNT_MISMATCH,
                      outcomes[("Sig1", 1, "h_1000_slots")]["error"])


class TestV1EvidenceStaysReplayable(BatchBase):
    """V1's transport is superseded, but the exchanges it wrote are still on disk and still evidence.

    The per-account replay is kept for exactly that reason: a live V1 run recorded 537 checkpoints
    under `getAccountInfo`, and dropping the reader would make that evidence unreadable.
    """

    def test_a_v1_shaped_exchange_still_rebuilds(self):
        raw = self.raw()
        row = {"signature": "Sig1", "delay_slots": 1, "horizon": "h_1000_slots",
               "bonding_curve": CURVE, "t0_slot": T0, "target_slot": T0 + 1001, "attempts": 0}
        outcome = B15N.read_checkpoint(row, "https://example.invalid", self.document,
                                       B15B.build_decoder(), raw,
                                       opener_for([account_response(row["target_slot"])]),
                                       lambda _s: None)
        raw.close()
        rebuilt = B15N.replay_checkpoints(self.directory / "raw.jsonl", self.document,
                                         B15B.build_decoder())
        key = ("Sig1", 1, "h_1000_slots")
        self.assertIn(key, rebuilt)
        self.assertEqual(rebuilt[key]["virtual_quote"], outcome["state"]["virtual_quote"])
        self.assertEqual(rebuilt[key]["context_slot"], outcome["context_slot"])

    def test_replaying_a_missing_v1_log_refuses(self):
        with self.assertRaises(B15N.ExitCheckpointRefused) as caught:
            B15N.replay_checkpoints(self.directory / "absent.jsonl", self.document,
                                    B15B.build_decoder())
        self.assertIn("no raw exchange log", str(caught.exception))

    def test_the_two_replays_do_not_read_each_others_exchanges(self):
        """A batched exchange is not a per-account one, and neither reader may guess."""
        raw = self.raw()
        rows = self.rows(1)
        B15N.read_batch(rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
                        opener_for([batch_response(T0 + 1001, ["Curve0"])]), lambda _s: None)
        raw.close()
        self.assertEqual(B15N.replay_checkpoints(self.directory / "raw.jsonl", self.document,
                                                 B15B.build_decoder()), {})
        self.assertEqual(len(B15N.replay_batched_checkpoints(
            self.directory / "raw.jsonl", B15B.build_decoder())), 1)


class TestCrashAndRestart(BatchBase):
    def test_a_crash_between_raw_preservation_and_the_derived_write_loses_no_evidence(self):
        """The exchange is on disk before any element is judged, so the read is replayable."""
        raw = self.raw()
        rows = self.rows(2)
        outcomes, _served = B15N.read_batch(
            rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
            opener_for([batch_response(T0 + 1002, ["Curve0", "Curve1"])]), lambda _s: None)
        raw.close()
        # ... the process dies here, before a single row reaches the database ...
        connection = B15N.open_database(self.directory / "db.sqlite")
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM checkpoint").fetchone()[0], 0)
        connection.close()
        rebuilt = B15N.replay_batched_checkpoints(self.directory / "raw.jsonl",
                                                 B15B.build_decoder())
        self.assertEqual(len(rebuilt), 2)
        for key, outcome in outcomes.items():
            self.assertEqual(rebuilt[key]["virtual_quote"], outcome["state"]["virtual_quote"])
            self.assertEqual(rebuilt[key]["request_index"], outcome["request_index"])

    def test_the_replay_rejects_an_index_that_no_longer_names_its_curve(self):
        raw = self.raw()
        rows = self.rows(2)
        B15N.read_batch(rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw,
                        opener_for([batch_response(T0 + 1002, ["Curve0", "Curve1"])]),
                        lambda _s: None)
        raw.close()
        path = self.directory / "raw.jsonl"
        record = json.loads(path.read_text().strip())
        record["targets"][0]["request_index"] = 1        # now names the wrong curve
        path.write_text(json.dumps(record) + "\n")
        rebuilt = B15N.replay_batched_checkpoints(path, B15B.build_decoder())
        self.assertEqual(len(rebuilt), 1)                # the tampered one is dropped

    def test_a_batch_discarded_for_length_leaves_its_targets_retryable(self):
        connection = B15N.open_database(self.directory / "db.sqlite")
        rows = self.rows(2)
        for row in rows:
            connection.execute(
                "INSERT INTO schedule(signature,delay_slots,horizon,mint,bonding_curve,t0_slot,"
                "target_slot,state,reason,attempts,fork_state_at_schedule,observed_after_gap,"
                "scheduled_at_wall_unix,scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["signature"], row["delay_slots"], row["horizon"], "M", row["bonding_curve"],
                 T0, row["target_slot"], B15N.STATE_SCHEDULED, None, 0, "confirmed", 0, 0.0, 0))
        connection.commit()
        raw = self.raw()
        counts = B15N.drain_batched(
            connection, rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw, {},
            opener_for([batch_response(T0 + 1002, ["Curve0", "Curve1"], drop=1)]),
            lambda _s: None, self.b15i)
        raw.close()
        self.assertEqual(counts[B15N.N_BATCH_LENGTH], 2)
        states = {row[0] for row in connection.execute("SELECT state FROM schedule")}
        self.assertEqual(states, {B15N.STATE_SCHEDULED})   # still retryable while the deadline holds
        connection.close()

    def test_the_drain_terminates_when_every_batch_fails(self):
        """A discarded batch must not be retried forever inside one drain."""
        connection = B15N.open_database(self.directory / "db.sqlite")
        rows = self.rows(5)
        raw = self.raw()
        counts = B15N.drain_batched(
            connection, rows, "https://example.invalid", self.v2, B15B.build_decoder(), raw, {},
            opener_for([batch_response(T0 + 1005, ["Curve0"], drop=1)]),
            lambda _s: None, self.b15i)
        raw.close()
        connection.close()
        self.assertEqual(counts["batched_requests"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
