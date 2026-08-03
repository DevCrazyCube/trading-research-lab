"""B15q tests. Written and run while B15P is incomplete, on synthetic fixtures.

Two properties matter most and both are driven rather than argued: that nothing is materialized from
an incomplete backfill, and that a missing t0 fee schedule is never filled from anywhere. The second
is the one that would silently corrupt every priced cell, because a fee taken from a later trade
looks exactly like a fee that was known at t0.
"""
import hashlib
import importlib.util
import json
import pathlib
import random
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


B15Q = _load("b15q_clean_replication", "b15q_clean_replication.py")
B15P, B15L, B15M = B15Q.B15P, B15Q.B15L, B15Q.B15M
# Imported by the TESTS only, to cross-check the admissibility criterion. The study must not import
# it, and the dependency audit enforces that.
B15N = _load("b15n_native_exit_checkpoints", "b15n_native_exit_checkpoints.py")

NATIVE = B15L.NATIVE_QUOTE_MINT
DELAYS = (1, 2, 4)
HORIZONS = (("h_1000_slots", 1000), ("h_10000_slots", 10_000))
SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
MEMBER_SET_SHA = "661f953a3aa995abe9a013e69da080f71bad212666a40610d859764b2855a296"


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15q_"))
        self.work = self.directory / "b15q"
        self.b15p = self.directory / "b15p"
        self.b15p.mkdir(parents=True)
        self.b15i = self.directory / "processed_feed.sqlite"
        self.b15n = self.directory / "exit_checkpoints.sqlite"
        self.artifact = self.directory / "b15o.json"
        self.document = B15Q.verify_preregistration()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    # -- synthetic evidence ------------------------------------------------------------------

    def launches(self, count):
        return [(f"Sig{i:04d}", 436_984_400 + i, f"Mint{i}", f"Curve{i}") for i in range(count)]

    def write_b15o(self, launches):
        members = [{"signature": s, "t0_slot": t, "mint": m} for s, t, m, _c in launches]
        artifact = {"population": {"members": len(members), "first_member": members[0],
                                   "last_member": members[-1],
                                   "canonical_order": "t0_slot, signature, mint"}}
        self.artifact.write_bytes(json.dumps(artifact).encode())
        return members

    def write_b15n(self, launches, complete=False, real_quote=10 ** 12,
                   virtual_quote=10 ** 11, fork="confirmed", verdict=None, curve_override=None):
        connection = sqlite3.connect(self.b15n)
        connection.executescript(B15N.SCHEMA)
        for signature, t0, mint, curve in launches:
            for delay in DELAYS:
                for horizon, slots in HORIZONS:
                    target = t0 + delay + slots
                    connection.execute(
                        "INSERT INTO schedule(signature,delay_slots,horizon,mint,bonding_curve,"
                        "t0_slot,target_slot,state,reason,attempts,fork_state_at_schedule,"
                        "observed_after_gap,scheduled_at_wall_unix,scheduled_at_slot) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (signature, delay, horizon, mint,
                         curve_override or curve, t0, target, "checkpointed", None, 1,
                         "confirmed", 0, 0.0, t0))
                    connection.execute(
                        "INSERT INTO checkpoint(signature,delay_slots,horizon,target_slot,"
                        "context_slot,lateness_slots,virtual_quote,virtual_token,real_quote,"
                        "real_token,quote_mint,mayhem_mode,complete,fork_state_at_read,"
                        "chain_verdict,observed_after_gap,raw_sha256,latency_ns,attempts,"
                        "read_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (signature, delay, horizon, target, target, 0, virtual_quote,
                         1_038_580_645_161_290, real_quote, 758_680_645_161_290, NATIVE, 0,
                         int(complete), fork, verdict, 0, "a" * 64, 1000, 1, 0.0))
        connection.commit()
        connection.close()

    def write_b15i(self, launches):
        connection = sqlite3.connect(self.b15i)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS observation(signature TEXT PRIMARY KEY, t0_slot INTEGER, "
            "mint TEXT, bonding_curve TEXT, fork_state TEXT, observed_after_gap INTEGER, "
            "chain_verdict TEXT)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS target(signature TEXT, delay_slots INTEGER, "
            "bonding_curve TEXT, context_slot INTEGER, lateness_slots INTEGER, "
            "virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER, "
            "real_token INTEGER, quote_mint TEXT, mayhem_mode INTEGER, complete INTEGER, "
            "state TEXT)")
        for signature, t0, mint, curve in launches:
            connection.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?)",
                               (signature, t0, mint, curve, "confirmed", 0, "confirmed"))
            for delay in DELAYS:
                connection.execute(
                    "INSERT INTO target VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (signature, delay, curve, t0 + delay, 0, 30_000_000_000,
                     1_073_000_000_000_000, 0, 793_100_000_000_000, NATIVE, 0, 0, "captured"))
        connection.commit()
        connection.close()

    def write_b15p(self, launches, retrieved=None, no_trade=(), incomplete=0):
        """B15P's table: a retrieved schedule per launch unless it is listed as no-trade."""
        connection = B15P.open_database(self.b15p / "fee_schedules.sqlite")
        rows = launches[:len(launches) - incomplete]
        for signature, t0, mint, _curve in rows:
            if signature in no_trade:
                connection.execute(
                    "INSERT OR REPLACE INTO fee_schedule(signature,t0_slot,mint,state,reason,"
                    "attempts,recorded_at_wall_unix) VALUES (?,?,?,?,?,?,?)",
                    (signature, t0, mint, B15P.STATE_REFUSED,
                     f"{B15P.P_NO_TRADE_EVENT}: no TradeEvent", 1, 0.0))
                continue
            schedule = (retrieved or {}).get(signature, SCHEDULE)
            connection.execute(
                "INSERT OR REPLACE INTO fee_schedule(signature,t0_slot,mint,state,reason,fee_bps,"
                "creator_fee_bps,cashback_fee_bps,buyback_fee_bps,raw_sha256,attempts,"
                "recorded_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (signature, t0, mint, B15P.STATE_RETRIEVED, None, schedule["fee_bps"],
                 schedule["creator_fee_bps"], schedule["cashback_fee_bps"],
                 schedule["buyback_fee_bps"], "b" * 64, 1, 0.0))
        connection.commit()
        connection.close()

    def synthetic_document(self, members):
        """A freeze copy bound to the synthetic artifact and roster."""
        document = json.loads(json.dumps(self.document))
        document["bound_hashes"]["b15o_artifact_sha256"] = hashlib.sha256(
            self.artifact.read_bytes()).hexdigest()
        document["bound_hashes"]["member_set_sha256"] = B15P.member_set_hash(members)
        return document

    def b15p_document(self, members):
        document = json.loads(json.dumps(B15P.verify_preregistration()))
        frozen = document["the_frozen_member_set"]
        frozen["size"] = len(members)
        frozen["member_set_sha256"] = B15P.member_set_hash(members)
        frozen["b15o_artifact_sha256"] = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        return document

    def prepare(self, count=3, **kwargs):
        launches = self.launches(count)
        members = self.write_b15o(launches)
        self.write_b15n(launches, complete=kwargs.pop("complete", False),
                        curve_override=kwargs.pop("curve_override", None))
        self.write_b15i(launches)
        self.write_b15p(launches, no_trade=kwargs.pop("no_trade", ()),
                        retrieved=kwargs.pop("retrieved", None),
                        incomplete=kwargs.pop("incomplete", 0))
        return launches, members

    def run_materialize(self, members, **kwargs):
        document = self.synthetic_document(members)
        b15p_document = self.b15p_document(members)
        original = B15P.verify_preregistration
        B15P.verify_preregistration = lambda *a, **k: b15p_document
        try:
            return B15Q.materialize(self.work, document, self.artifact, self.b15i, self.b15n,
                                    self.b15p, verify_manifest=False, **kwargs)
        finally:
            B15P.verify_preregistration = original

    def run_status(self, members):
        document = self.synthetic_document(members)
        b15p_document = self.b15p_document(members)
        original = B15P.verify_preregistration
        B15P.verify_preregistration = lambda *a, **k: b15p_document
        try:
            return B15Q.status(self.work, document, self.artifact, self.b15n, self.b15p)
        finally:
            B15P.verify_preregistration = original


class TestFreeze(Base):
    def test_the_freeze_is_pinned(self):
        self.assertEqual(self.document["preregistration_id"], "B15Q_CLEAN_REPLICATION_V1")
        self.assertTrue(self.document["committed_before_reading_any_strategy_quantity"])

    def test_b15q_supersedes_nothing_and_never_touches_b15o(self):
        self.assertIsNone(self.document["supersedes"])
        self.assertIn("does not replace", self.document["supersedes_nothing_reason"])
        source = (ROOT / "scripts" / "b15q_clean_replication.py").read_text()
        for forbidden in ("b15o/replication.json\", \"w", "B15O_ARTIFACT.write", "unlink"):
            self.assertNotIn(forbidden, source)

    def test_every_bound_hash_is_the_real_one(self):
        self.assertTrue(B15Q.verify_bound_hashes())

    def test_a_drifted_bound_document_refuses(self):
        document = json.loads(json.dumps(self.document))
        document["bound_hashes"]["b15l_preregistration_canonical_sha256"] = "0" * 64
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.verify_bound_hashes(document)
        self.assertIn(B15Q.Q_HASH_DRIFT, str(caught.exception))

    def test_a_drifted_b15o_artifact_refuses(self):
        self.artifact.write_bytes(b"{}")
        document = json.loads(json.dumps(self.document))
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.verify_bound_hashes(document, self.artifact)
        self.assertIn(B15Q.Q_HASH_DRIFT, str(caught.exception))

    def test_a_tampered_freeze_refuses(self):
        altered = self.directory / "altered.json"
        document = json.loads(B15Q.PREREG_PATH.read_bytes())
        document["bound_hashes"]["member_set_sha256"] = "0" * 64
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.verify_preregistration(altered)
        self.assertIn("pinned", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15Q.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        poisoned = self.directory / "poisoned.py"
        poisoned.write_text("EXECUTION_SURFACE_TOKENS = ()\nx = 'sendTransaction'\n")
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.assert_no_execution_surface(poisoned)
        self.assertIn("sendTransaction", str(caught.exception))


class TestDependencyAudit(Base):
    def test_the_closure_references_only_the_anticipated_families(self):
        audit = B15Q.assert_dependencies_declared()
        self.assertTrue(audit["all_declared"])
        for name in audit["forbidden_references"]:
            self.assertTrue(name.startswith(("b15a_", "b15b_", "b15c_", "b15d_", "b15e_",
                                             "b15f_", "b15g_", "b15h_", "b15j_", "b15l_",
                                             "b15m_")), name)

    def test_the_fee_schedules_reader_is_never_called(self):
        """The function that reads B15b and caused B15O's empty result."""
        self.assertTrue(B15Q.assert_fee_schedules_reader_never_called())

    def test_calling_the_fee_schedules_reader_is_caught(self):
        poisoned = self.directory / "leaky.py"
        poisoned.write_text(
            "def assert_fee_schedules_reader_never_called():\n    pass\n"
            "def go():\n    return B15L.fee_schedules({'x'})\n")
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.assert_fee_schedules_reader_never_called(poisoned)
        self.assertIn(B15Q.Q_FORBIDDEN_DEPENDENCY, str(caught.exception))

    def test_the_runtime_guard_refuses_a_forbidden_open(self):
        for token in ("b15a", "b15b", "b15f"):
            with self.subTest(token=token):
                with self.assertRaises(B15P.BackfillRefused):
                    with B15P.PathGuard():
                        (ROOT / "research" / token / "anything").read_text()

    def test_injection_means_the_studies_open_nothing(self):
        """B15L and B15M carry dirty closures; injection is why that is admissible."""
        launches, members = self.prepare()
        with B15P.PathGuard() as guard:
            self.run_materialize(members)
        forbidden = [path for path in guard.opened
                     if "/b15a/" in path or "/b15b/" in path or "/b15f/" in path]
        self.assertEqual(forbidden, [])

    def test_a_freeze_with_no_manifest_requirement_refuses(self):
        document = json.loads(json.dumps(self.document))
        del document["inputs"]["b15l_and_b15m_are_imported_and_their_closures_are_dirty"][
            "declared_manifest_required"]
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.assert_dependencies_declared(document)
        self.assertIn(B15Q.Q_FORBIDDEN_DEPENDENCY, str(caught.exception))

    def test_a_forbidden_reference_outside_the_declared_families_refuses(self):
        """B15N is the real case: its isolation guard carries bare forbidden literals.

        This is why the study applies the exit-admissibility criterion itself instead of importing
        B15N — and this test proves the audit would have refused had it not.
        """
        original = B15P.module_closure
        B15P.module_closure = lambda entry: {"b15n_native_exit_checkpoints.py"}
        try:
            with self.assertRaises(B15Q.ReplicationRefused) as caught:
                B15Q.assert_dependencies_declared(self.document)
        finally:
            B15P.module_closure = original
        self.assertIn(B15Q.Q_FORBIDDEN_DEPENDENCY, str(caught.exception))
        self.assertIn("b15n_native_exit_checkpoints.py", str(caught.exception))

    def test_the_admissibility_criterion_agrees_with_b15n_on_every_state(self):
        """Applied here rather than imported, so it is cross-checked instead of trusted."""
        for fork in ("confirmed", "processed_unconfirmed", "unresolved", "orphaned", None):
            for verdict in ("confirmed", "not_found", None):
                with self.subTest(fork=fork, verdict=verdict):
                    self.assertEqual(B15Q.admissible_exit(fork, verdict),
                                     B15N.admissible_downstream(fork, verdict))


class TestLockedWhileB15pIncomplete(Base):
    def test_an_incomplete_backfill_locks_the_study(self):
        _launches, members = self.prepare(count=3, incomplete=1)
        state = self.run_status(members)
        self.assertTrue(state["locked"])
        self.assertIn(B15Q.Q_B15P_INCOMPLETE, state["reasons"])
        self.assertEqual(state["b15p"]["remaining"], 1)

    def test_materializing_while_locked_refuses_and_writes_nothing(self):
        _launches, members = self.prepare(count=3, incomplete=1)
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            self.run_materialize(members)
        self.assertIn(B15Q.Q_B15P_INCOMPLETE, str(caught.exception))
        self.assertFalse((self.work / "replication.json").exists())

    def test_an_absent_backfill_locks_the_study(self):
        launches = self.launches(2)
        members = self.write_b15o(launches)
        self.write_b15n(launches)
        self.write_b15i(launches)
        state = self.run_status(members)
        self.assertTrue(state["locked"])
        self.assertIn(B15Q.Q_B15P_INCOMPLETE, state["reasons"])

    def test_the_locked_status_publishes_no_strategy_quantity(self):
        _launches, members = self.prepare(count=3, incomplete=1)
        state = self.run_status(members)
        text = json.dumps(state).lower()
        for banned in ("counterfactual_net", "capacity_by", "self_impact", "priced_cells",
                       "order_statistic"):
            self.assertNotIn(banned, text)
        self.assertTrue(state["reports_no_strategy_quantity_while_locked"])

    def test_a_member_set_drift_locks_the_study(self):
        _launches, members = self.prepare()
        document = self.synthetic_document(members)
        document["bound_hashes"]["member_set_sha256"] = "0" * 64
        b15p_document = self.b15p_document(members)
        original = B15P.verify_preregistration
        B15P.verify_preregistration = lambda *a, **k: b15p_document
        try:
            state = B15Q.status(self.work, document, self.artifact, self.b15n, self.b15p)
        finally:
            B15P.verify_preregistration = original
        self.assertTrue(state["locked"])
        self.assertIn(B15Q.Q_MEMBER_SET_DRIFT, state["reasons"])

    def test_a_failing_b15p_manifest_refuses(self):
        _launches, members = self.prepare()
        document = self.synthetic_document(members)
        b15p_document = self.b15p_document(members)
        original = B15P.verify_preregistration
        B15P.verify_preregistration = lambda *a, **k: b15p_document
        try:
            # verify_manifest=True with no raw log present: the replay cannot be performed.
            with self.assertRaises(B15Q.ReplicationRefused) as caught:
                B15Q.materialize(self.work, document, self.artifact, self.b15i, self.b15n,
                                 self.b15p, verify_manifest=True)
            self.assertIn(B15Q.Q_B15P_MANIFEST_FAILED, str(caught.exception))
        finally:
            B15P.verify_preregistration = original


class TestNoFutureLeakage(Base):
    def test_a_member_without_a_t0_schedule_is_coverage_not_failure(self):
        launches, members = self.prepare(count=3, no_trade={"Sig0000"})
        report = self.run_materialize(members)["report"]
        population = report["population"]
        self.assertEqual(population["members_without_a_t0_fee_schedule"], 1)
        self.assertIn(B15P.P_NO_TRADE_EVENT, population["t0_fee_unavailable_by_reason"])
        self.assertIn("no retry can supply one",
                      population["t0_fee_unavailability_is_coverage_not_failure"])

    def test_the_member_without_a_schedule_is_simply_absent_from_the_schedules(self):
        launches, _members = self.prepare(count=3, no_trade={"Sig0000"})
        schedules, unavailable = B15Q.load_fee_schedules(self.b15p)
        self.assertNotIn("Sig0000", schedules)
        self.assertEqual(unavailable["Sig0000"], B15P.P_NO_TRADE_EVENT)

    def test_a_schedule_filled_from_a_later_trade_is_refused(self):
        """The attempt this study exists to make impossible."""
        launches, members = self.prepare(count=3, no_trade={"Sig0000"})
        schedules, _unavailable = B15Q.load_fee_schedules(self.b15p)
        # Somebody fills the gap from a later trade on the same curve.
        schedules["Sig0000"] = dict(SCHEDULE, fee_bps=100)
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.assert_no_future_leakage(schedules, members, self.b15p)
        self.assertIn(B15Q.Q_FUTURE_LEAKAGE, str(caught.exception))
        self.assertIn("filled from outside the launch transaction", str(caught.exception))

    def test_a_schedule_for_a_non_member_is_refused(self):
        launches, members = self.prepare(count=3)
        schedules, _unavailable = B15Q.load_fee_schedules(self.b15p)
        schedules["NotAMember"] = SCHEDULE
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.assert_no_future_leakage(schedules, members, self.b15p)
        self.assertIn("belong to no member", str(caught.exception))

    def test_clean_schedules_pass_the_leakage_guard(self):
        launches, members = self.prepare(count=3)
        schedules, _unavailable = B15Q.load_fee_schedules(self.b15p)
        self.assertTrue(B15Q.assert_no_future_leakage(schedules, members, self.b15p))

    def test_the_freeze_forbids_filling_from_any_post_t0_source(self):
        rule = self.document["no_trade_event_is_coverage_not_failure"]
        text = json.dumps(rule).lower()
        for source in ("later trade", "modal value", "another member"):
            self.assertIn(source, text)
        self.assertIn("future leakage", text)


class TestSchedulesAndJoin(Base):
    def test_one_schedule_per_member(self):
        launches, _members = self.prepare(count=3)
        schedules, _unavailable = B15Q.load_fee_schedules(self.b15p)
        self.assertEqual(len(schedules), 3)
        self.assertEqual(len(set(map(tuple, (sorted(s.items()) for s in schedules.values())))), 1)

    def test_fee_variants_are_carried_through_as_they_are(self):
        launches = self.launches(3)
        members = self.write_b15o(launches)
        self.write_b15n(launches)
        self.write_b15i(launches)
        variants = {"Sig0000": dict(SCHEDULE, creator_fee_bps=0, cashback_fee_bps=30),
                    "Sig0001": dict(SCHEDULE, buyback_fee_bps=0),
                    "Sig0002": dict(SCHEDULE, fee_bps=100)}
        self.write_b15p(launches, retrieved=variants)
        schedules, _unavailable = B15Q.load_fee_schedules(self.b15p)
        for signature, expected in variants.items():
            self.assertEqual(schedules[signature], expected)

    def test_uniqueness_dropped_from_b15ps_store_refuses(self):
        """One schedule per member is the store's guarantee; if it lapses, this reader refuses."""
        launches, _members = self.prepare(count=2)
        path = self.b15p / "fee_schedules.sqlite"
        connection = sqlite3.connect(path)
        rows = connection.execute("SELECT * FROM fee_schedule").fetchall()
        connection.execute("DROP TABLE fee_schedule")
        connection.execute(
            "CREATE TABLE fee_schedule (signature TEXT, t0_slot INTEGER, mint TEXT, state TEXT, "
            "reason TEXT, fee_bps INTEGER, creator_fee_bps INTEGER, cashback_fee_bps INTEGER, "
            "buyback_fee_bps INTEGER, raw_sha256 TEXT, attempts INTEGER, latency_ns INTEGER, "
            "recorded_at_wall_unix REAL)")
        connection.executemany(
            f"INSERT INTO fee_schedule VALUES ({','.join('?' * len(rows[0]))})", rows + rows)
        connection.commit()
        connection.close()
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.load_fee_schedules(self.b15p)
        self.assertIn(B15Q.Q_SCHEDULE_NOT_UNIQUE, str(caught.exception))

    def test_an_absent_published_operand_refuses(self):
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.published_operands({"b15l_v1": self.directory / "not_published.md"})
        self.assertIn(B15Q.Q_EVIDENCE_INSUFFICIENT, str(caught.exception))

    def test_the_real_published_operands_are_all_present(self):
        operands = B15Q.published_operands()
        self.assertEqual(sorted(operands), ["b15l_v1", "b15m_v1", "b15o"])

    def test_a_join_identity_mismatch_refuses(self):
        launches = self.launches(2)
        members = self.write_b15o(launches)
        self.write_b15i(launches)
        self.write_b15n(launches, curve_override="SomeOtherCurve")
        self.write_b15p(launches)
        entries = B15Q.load_entries(members, self.b15i)
        exits, _withheld = B15Q.load_exits(members, self.b15n)
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.assert_join_identity(entries, exits)
        self.assertIn(B15Q.Q_JOIN_IDENTITY, str(caught.exception))

    def test_a_matching_join_passes(self):
        launches, members = self.prepare(count=2)
        entries = B15Q.load_entries(members, self.b15i)
        exits, _withheld = B15Q.load_exits(members, self.b15n)
        self.assertTrue(B15Q.assert_join_identity(entries, exits))

    def test_an_unconfirmed_exit_is_withheld_and_counted(self):
        launches = self.launches(2)
        members = self.write_b15o(launches)
        self.write_b15i(launches)
        self.write_b15n(launches, fork="unresolved", verdict=None)
        self.write_b15p(launches)
        exits, withheld = B15Q.load_exits(members, self.b15n)
        self.assertEqual(len(exits), 0)
        self.assertEqual(withheld, len(launches) * len(DELAYS) * len(HORIZONS))

    def test_a_missing_input_artifact_refuses(self):
        launches, members = self.prepare(count=2)
        with self.assertRaises(B15Q.ReplicationRefused) as caught:
            B15Q.load_entries(members, self.directory / "absent.sqlite")
        self.assertIn(B15Q.Q_EVIDENCE_INSUFFICIENT, str(caught.exception))


class TestMaterialization(Base):
    def test_a_complete_backfill_materializes_both_studies(self):
        _launches, members = self.prepare(count=3)
        outcome = self.run_materialize(members)
        report = outcome["report"]
        self.assertFalse(outcome["already_materialized"])
        self.assertEqual(report["replicated"]["b15l_counterfactual"]["label"],
                         "COUNTERFACTUAL_UNREACTING_BOOK")
        self.assertEqual(report["replicated"]["b15m_capacity"]["label"],
                         "LIQUIDITY_CAPACITY_DIAGNOSTIC")
        self.assertEqual(report["population"]["members"], 3)
        self.assertTrue((self.work / "replication.json").exists())

    def test_the_second_call_reports_rather_than_recomputes(self):
        _launches, members = self.prepare(count=3)
        first = self.run_materialize(members)
        second = self.run_materialize(members)
        self.assertTrue(second["already_materialized"])
        self.assertIn(B15Q.Q_ALREADY_MATERIALIZED, second["note"])
        self.assertEqual(json.dumps(first["report"]["replicated"], sort_keys=True),
                         json.dumps(second["report"]["replicated"], sort_keys=True))

    def test_the_artifact_is_byte_stable_across_readings(self):
        _launches, members = self.prepare(count=3)
        self.run_materialize(members)
        path = self.work / "replication.json"
        self.assertEqual(path.read_bytes(), path.read_bytes())

    def test_the_false_censoring_prose_is_superseded_and_preserved(self):
        _launches, members = self.prepare(count=3)
        report = self.run_materialize(members)["report"]
        for key in ("b15l_counterfactual", "b15m_capacity"):
            block = report["replicated"][key]
            superseded = block["inherited_censoring_statement_superseded"]
            self.assertTrue(superseded["false_for_this_population"])
            self.assertIn("B15f schedules from B15a", superseded["statement"])
            self.assertIn("descend from B15i's own observations", block["censoring_statement"])
            self.assertNotIn("B15f schedules from B15a", block["censoring_statement"])

    def test_b15ls_own_document_is_not_edited(self):
        """Their prose is correct for the population they ran on."""
        self.assertIn("B15f schedules from B15a", B15L.CENSORING_STATEMENT)

    def test_the_report_carries_all_three_operands_by_hash(self):
        _launches, members = self.prepare(count=3)
        report = self.run_materialize(members)["report"]
        for key in ("b15l_v1", "b15m_v1", "b15o"):
            self.assertEqual(len(report["published_operands"][key]["sha256"]), 64)
        self.assertEqual(report["comparison"]["nature"], "DESCRIPTIVE ONLY")

    def test_the_report_declares_no_verdict_and_no_pooling(self):
        _launches, members = self.prepare(count=3)
        report = self.run_materialize(members)["report"]
        keys = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    keys.add(str(key).lower())
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(report)
        for banned in ("verdict", "passed", "agreement", "pooled", "success", "return", "profit"):
            self.assertNotIn(banned, keys)

    def test_the_report_states_b15o_is_untouched(self):
        _launches, members = self.prepare(count=3)
        report = self.run_materialize(members)["report"]
        self.assertIn("neither edited, replaced nor re-run", report["b15o_is_untouched"])

    def test_the_result_is_identical_under_evidence_permutation(self):
        launches = self.launches(4)
        shuffled = list(launches)
        random.Random(4).shuffle(shuffled)
        members = self.write_b15o(launches)
        self.write_b15n(shuffled)
        self.write_b15i(shuffled)
        self.write_b15p(shuffled)
        first = self.run_materialize(members)["report"]
        second_work = self.directory / "b15q_two"
        # Fresh evidence files, so the second run's row order really is the reversed one: rewriting
        # the same tables would only append, and insertion order is what a table scan returns.
        reversed_order = list(reversed(shuffled))
        self.b15i.unlink()
        self.b15n.unlink()
        shutil.rmtree(self.b15p)
        self.b15p.mkdir()
        self.write_b15n(reversed_order)
        self.write_b15i(reversed_order)
        self.write_b15p(reversed_order)
        document = self.synthetic_document(members)
        b15p_document = self.b15p_document(members)
        original = B15P.verify_preregistration
        B15P.verify_preregistration = lambda *a, **k: b15p_document
        try:
            second = B15Q.materialize(second_work, document, self.artifact, self.b15i, self.b15n,
                                      self.b15p, verify_manifest=False)["report"]
        finally:
            B15P.verify_preregistration = original
        self.assertEqual(json.dumps(first["replicated"], sort_keys=True),
                         json.dumps(second["replicated"], sort_keys=True))

    def test_a_completed_curve_at_exit_is_refused_by_b15ls_own_gate(self):
        _launches, members = self.prepare(count=3, complete=True)
        report = self.run_materialize(members)["report"]
        self.assertIn(B15L.L_COMPLETE_BY_EXIT,
                      report["replicated"]["b15l_counterfactual"]["refusals"])

    def test_no_curve_formula_is_duplicated_here(self):
        source = (ROOT / "scripts" / "b15q_clean_replication.py").read_text()
        self.assertIn("B15L.run(", source)
        self.assertIn("B15M.run(", source)
        for banned in ("tokens_out_for_exact_quote_in", "quote_out_for_tokens_in",
                       "def price_entry", "def price_exit", "def external_capacity"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
