"""Sealing a finished B9d raw collection.

The seal is the one deliberate write in the pre-decode sequence, so what it refuses matters more
than what it writes.
"""
import fcntl
import importlib.util
import pathlib
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9g_seal_collection", ROOT / "scripts" / "b9g_seal_collection.py")
SEAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEAL)

# One b9d instance, so the fixture's patched population constants are the ones the seal verifies
# against. See the same note in test_b9g_decode_readiness.
B9D = B9DT.B9D
SEAL.B9D = B9D
SEAL.FreezeViolation = B9D.FreezeViolation


class SealFixture(B9DT.PublicationGateTests):
    """Borrows the complete-artifact fixture; the parent's own tests are not re-run here."""

    def setUp(self):
        super().setUp()
        self.lock_path = pathlib.Path(f"{self.path}.collector.lock")


for _name in [n for n in dir(B9DT.PublicationGateTests) if n.startswith("test_")]:
    setattr(SealFixture, _name, None)


class SealCollectionTests(SealFixture):

    def marker(self):
        database = self.open()
        row = database.execute(
            "SELECT value FROM metadata WHERE key=?", (B9D.COLLECTION_COMPLETE_KEY,)).fetchone()
        return row[0] if row else None

    def test_a_complete_artifact_seals_and_records_the_marker(self):
        report = SEAL.seal_collection(str(self.path), now=1234)
        self.assertEqual(report["sealed_at_unix"], "1234")
        self.assertFalse(report["already_sealed"])
        self.assertEqual(self.marker(), "1234")

    def test_sealing_twice_reports_the_original_and_does_not_re_stamp(self):
        """A later, possibly partial, state must never be able to re-stamp the artifact."""
        SEAL.seal_collection(str(self.path), now=1234)
        again = SEAL.seal_collection(str(self.path), now=9999)
        self.assertEqual(again["sealed_at_unix"], "1234")
        self.assertTrue(again["already_sealed"])
        self.assertEqual(self.marker(), "1234")

    def test_a_live_collector_blocks_the_seal_and_keeps_its_lock(self):
        """Acquiring the collector's own lock IS the proof body collection has exited.

        The seal runs after a natural exit; it must never be able to force one, so a held lock
        refuses rather than waiting.
        """
        holder = self.lock_path.open("a+b")
        self.addCleanup(holder.close)
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            SEAL.seal_collection(str(self.path))
        self.assertIn("single-writer lock", str(ctx.exception))
        self.assertIsNone(self.marker(), "a refused seal must write nothing")
        second = self.lock_path.open("a+b")
        self.addCleanup(second.close)
        with self.assertRaises(BlockingIOError):
            fcntl.flock(second.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_a_partial_population_refuses_and_writes_no_marker(self):
        """The seal must mean the frozen set was preserved, not that the collector stopped."""
        database = self.open()
        with database:
            database.execute("DELETE FROM raw_transaction WHERE signature=?", ("sigA",))
        database.close()
        with self.assertRaises(B9D.FreezeViolation):
            SEAL.seal_collection(str(self.path))
        self.assertIsNone(self.marker())

    def test_a_body_without_its_coordinate_refuses(self):
        database = self.open()
        with database:
            database.execute("DELETE FROM transaction_coordinate WHERE signature=?", ("sigA",))
        database.close()
        with self.assertRaises(B9D.FreezeViolation):
            SEAL.seal_collection(str(self.path))
        self.assertIsNone(self.marker())

    def test_sealing_does_not_require_or_touch_boundary_evidence(self):
        """Body collection is closed FIRST; boundary evidence is collected in the natural gap after.

        Sealing a body collection that has no boundary evidence yet is the intended order, so the
        seal must not demand it. B9g is what requires boundary completeness, and only before decode.
        """
        database = self.open()
        with database:
            database.execute("DELETE FROM raw_boundary_response")
            database.execute("DELETE FROM metadata WHERE key='boundary_completed_at_unix'")
        database.close()
        self.assertEqual(SEAL.seal_collection(str(self.path), now=7)["sealed_at_unix"], "7")


if __name__ == "__main__":
    unittest.main()
