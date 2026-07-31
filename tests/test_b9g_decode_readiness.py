"""B9g decode-readiness gate.

Built on the same tiny complete artifact the publication gates use, so these tests exercise
readiness rather than re-testing the structural gates underneath it.
"""
import contextlib
import fcntl
import importlib.util
import signal
import pathlib
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9g_decode_readiness", ROOT / "scripts" / "b9g_decode_readiness.py")
B9G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9G)

# Every module here loads b9d by path, which produces a SEPARATE module object each time. The
# fixture patches EXPECTED_SLOTS/EXPECTED_SIGNATURES down to a two-signature population on ITS
# instance; B9g reading a different instance would see the real 94,985 and refuse a fixture that is
# complete by its own constants. Bind them to one object so the patch and the gate agree.
B9D = B9DT.B9D
B9G.B9D = B9D
# `FreezeViolation` must be rebound too. B9g captured it from its own b9d instance at import, and a
# class object from a different instance is a DIFFERENT class: `assertRaises` would not match it,
# so a correctly-raised refusal would read as an unexpected error.
B9G.FreezeViolation = B9D.FreezeViolation


class ReadinessFixture(B9DT.PublicationGateTests):
    """Reuses the complete-artifact fixture; overrides the inherited gate tests away."""

    def setUp(self):
        super().setUp()
        database = self.open()
        with database:
            B9D.mark_collection_complete(database)
        self.lock_path = pathlib.Path(f"{self.path}.collector.lock")
        self.lock_path.touch()

    def ready(self):
        return B9G.assert_decode_ready(self.open(), str(self.path))

    @contextlib.contextmanager
    def bounded(self, seconds=5):
        """Fail, rather than hang, if the readiness probe waits on the lock.

        A blocking `flock` would queue behind the live collector and eventually ACQUIRE the lock --
        the exact behaviour this gate must never have. Without a bound, a regression to blocking
        wedges the suite silently instead of reporting a defect.
        """
        def fire(signum, frame):
            raise TimeoutError(
                "the readiness probe blocked instead of refusing; it must never wait on a live "
                "collector's lock")

        previous = signal.signal(signal.SIGALRM, fire)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)

    # The parent class's own tests are not re-run here; this subclass only borrows its fixture.
    def __init_subclass__(cls, **kwargs):          # pragma: no cover - structural guard
        super().__init_subclass__(**kwargs)


# Referenced through the module so pytest does not collect the parent class a second
# time from this file; the subclass borrows the fixture, not the parent's tests.
for _name in [n for n in dir(B9DT.PublicationGateTests) if n.startswith("test_")]:
    setattr(ReadinessFixture, _name, None)


class DecodeReadinessTests(ReadinessFixture):

    def test_a_complete_unlocked_undecoded_artifact_is_ready(self):
        report = self.ready()
        self.assertTrue(report["ready"])
        self.assertTrue(report["collection_completed_at_unix"])
        self.assertEqual(report["verification"]["integrity"], "ok")

    def test_a_held_collector_lock_refuses_and_is_never_stolen(self):
        """A readiness check that can take the lock can stop the thing it is inspecting."""
        holder = self.lock_path.open("a+b")
        self.addCleanup(holder.close)
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.bounded():
            with self.assertRaises(B9D.FreezeViolation) as ctx:
                self.ready()
        self.assertIn("holds the single-writer lock", str(ctx.exception))
        # Still held by the original owner: the probe refused rather than queueing and acquiring.
        second = self.lock_path.open("a+b")
        self.addCleanup(second.close)
        with self.assertRaises(BlockingIOError):
            fcntl.flock(second.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_a_missing_completion_marker_refuses(self):
        """Row counts cannot distinguish a finished collector from one that stopped at exactly the
        right moment, because the counts are what resuming changes."""
        database = self.open()
        with database:
            database.execute("DELETE FROM metadata WHERE key=?", (B9D.COLLECTION_COMPLETE_KEY,))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.ready()
        self.assertIn("no verified-complete collection", str(ctx.exception))

    def test_the_marker_is_immutable_and_refuses_a_partial_population(self):
        """It must mean "completed having preserved the frozen set", not "stopped"."""
        database = self.open()
        first = database.execute(
            "SELECT value FROM metadata WHERE key=?", (B9D.COLLECTION_COMPLETE_KEY,)).fetchone()[0]
        with database:
            self.assertEqual(B9D.mark_collection_complete(database, now=999), first,
                             "a second call must not re-stamp the artifact")
        with database:
            database.execute("DELETE FROM metadata WHERE key=?", (B9D.COLLECTION_COMPLETE_KEY,))
            database.execute("DELETE FROM raw_transaction WHERE signature=?", ("sigA",))
        with self.assertRaises(B9D.FreezeViolation):
            with database:
                B9D.mark_collection_complete(database)
        self.assertIsNone(database.execute(
            "SELECT value FROM metadata WHERE key=?", (B9D.COLLECTION_COMPLETE_KEY,)).fetchone(),
            "a refused marking must leave no marker behind")

    def test_a_partial_population_refuses_even_with_a_stale_marker(self):
        """The marker is necessary, not sufficient: an artifact truncated after being marked must
        still fail the population gates."""
        database = self.open()
        with database:
            database.execute("DELETE FROM raw_transaction WHERE signature=?", ("sigA",))
        with self.assertRaises(B9D.FreezeViolation):
            self.ready()

    def test_a_body_with_no_coordinate_refuses(self):
        database = self.open()
        with database:
            database.execute("DELETE FROM transaction_coordinate WHERE signature=?", ("sigA",))
        with self.assertRaises(B9D.FreezeViolation):
            self.ready()

    def test_incomplete_boundary_evidence_refuses(self):
        """Boundary COMPLETENESS is required; boundary ORDERING deliberately is not.

        The evidence is collected after the bodies on purpose, to preserve the single-writer
        invariant, and finalized current ProgramData whose latest deploy precedes the observation
        start proves no in-range upgrade regardless of fetch order.
        """
        database = self.open()
        with database:
            database.execute("DELETE FROM raw_boundary_response WHERE program_id=?",
                             (B9D.PUMPSWAP_PROGRAM,))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.ready()
        self.assertIn("expected 2", str(ctx.exception))

    def test_partially_materialised_derived_rows_refuse(self):
        database = self.open()
        with database:
            database.execute(
                "INSERT INTO instruction (slot,transaction_index,outer_index,inner_index,"
                "signature,program_id,discriminator,idl_name,target,accounts_json,data_len) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (self.SLOT_A, 0, 0, -1, "sigA", B9D.PUMP_PROGRAM, "00" * 8, "buy", 1, "[]", 16))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.ready()
        self.assertIn("derived decoder output already exists", str(ctx.exception))

    def test_decode_metadata_alone_refuses_even_with_no_derived_rows(self):
        """A pass that wrote its metadata and left no rows is not an unstarted artifact."""
        database = self.open()
        with database:
            database.execute("INSERT INTO metadata(key,value) VALUES ('decoded_at_unix','1')")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.ready()
        self.assertIn("derived decoder output already exists", str(ctx.exception))

    def test_a_missing_lock_file_is_reported_not_treated_as_readiness(self):
        """Absence of a lock file means nothing can hold it, not that collection happened."""
        self.lock_path.unlink()
        report = self.ready()
        self.assertFalse(report["collector_lock_file_present"])
        self.assertTrue(report["ready"], "readiness rests on the marker and the population")


if __name__ == "__main__":
    unittest.main()
