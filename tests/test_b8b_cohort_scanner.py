"""Tests for the B8b cohort scanner.

The scanner draws the cohort every later result rests on, and its failure modes are quiet ones: a
schedule that drifts off its intended minutes, a resumed run that silently redraws the sample, or a
truncated run reported as a result. Each of those is pinned here.

Hermetic by construction — `_get_block_time` is stubbed, so no test reaches the network. Temp
databases only; the live artifact is never opened.
"""
import importlib.util
import pathlib
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "b8b", str(ROOT / "scripts" / "b8b_cohort_scanner.py"))
B8B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B8B)


class FrozenScheduleTests(unittest.TestCase):
    """The schedule is the sample definition. If it changes, the cohort changes."""

    def test_offsets_match_the_frozen_rule(self):
        self.assertEqual(B8B.STRIDE, 27)
        self.assertEqual(B8B.MODULUS, 59)
        self.assertEqual(B8B.BLOCK_MINUTES, 4)
        self.assertEqual(B8B.offsets(), [(27 * h) % 59 for h in range(24)])

    def test_offsets_are_distinct_so_the_sample_cannot_alias(self):
        """Two hours sharing a minute-of-hour would alias with hourly-periodic launchers."""
        self.assertEqual(len(set(B8B.offsets())), 24)

    def test_no_block_straddles_an_hour_boundary(self):
        self.assertLessEqual(max(B8B.offsets()) + B8B.BLOCK_MINUTES, 60)

    def test_every_minute_of_hour_is_reachable(self):
        """The original (7 mod 54) schedule could never sample minute 59 of any hour."""
        covered = set()
        for offset in B8B.offsets():
            covered |= set(range(offset, offset + B8B.BLOCK_MINUTES))
        self.assertEqual(covered, set(range(60)))

    def test_freeze_hash_is_the_one_the_owner_authorised(self):
        self.assertEqual(
            B8B.FREEZE_SHA256,
            "56d8a83b8cbc0821fabb5e5b8e098728caa2d7775d46f0c9fb55e673cf848374")


class BoundaryResolutionTests(unittest.TestCase):
    """Boundaries must come from chain time. Interpolation drifts, and drift moves the sample."""

    BASE, T0 = 1000, 500_000
    SKIPPED = frozenset(range(1050, 1060))      # a hole straddling a boundary

    def setUp(self):
        self.chain = {s: self.T0 + (s - self.BASE) * 2
                      for s in range(self.BASE, self.BASE + 500) if s not in self.SKIPPED}
        self._real = B8B._get_block_time
        B8B._get_block_time = lambda url, slot, retries: self.chain.get(slot)
        self.addCleanup(lambda: setattr(B8B, "_get_block_time", self._real))

    def search(self, target):
        return B8B.first_slot_at_or_after("url", target, self.BASE, self.BASE + 499, 1)

    def expected(self, target):
        candidates = sorted(s for s, t in self.chain.items() if t >= target)
        return candidates[0] if candidates else None

    def test_target_landing_inside_a_skipped_run_returns_the_next_real_slot(self):
        target = self.T0 + 2 * 51            # slot 1051 is skipped
        self.assertEqual(self.search(target), 1060)
        self.assertEqual(self.search(target), self.expected(target))

    def test_target_exactly_on_a_slot_returns_that_slot(self):
        target = self.T0 + 2 * 40
        self.assertEqual(self.search(target), 1040)

    def test_target_before_the_range_returns_the_first_slot(self):
        self.assertEqual(self.search(self.T0 - 100), self.BASE)

    def test_target_after_the_range_returns_none_rather_than_guessing(self):
        self.assertIsNone(self.search(self.T0 + 10_000))

    def test_unresolvable_boundary_fails_closed(self):
        """A boundary that cannot be placed must abort, never be approximated."""
        B8B._get_block_time = lambda url, slot, retries: None
        with self.assertRaises(SystemExit) as ctx:
            B8B.resolve_blocks("url", self.BASE, self.BASE + 499, self.T0, 1)
        self.assertIn("FAIL CLOSED", str(ctx.exception))


class ScheduleFreezingTests(unittest.TestCase):
    """A resumed run must reuse the stored schedule. Recomputing it would redraw the sample."""

    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "b8b_test.sqlite"
        self.connection = B8B.open_database(str(self.path))
        self.addCleanup(self.connection.close)
        self.blocks = [{"hour": h, "offset_minutes": (27 * h) % 59,
                        "start_slot": 1000 + h * 100, "end_slot_exclusive": 1000 + h * 100 + 50,
                        "start_time": 5000 + h * 3600, "end_time": 5000 + h * 3600 + 240}
                       for h in range(24)]

    def test_first_run_stores_the_schedule(self):
        stored, fresh = B8B.store_blocks(self.connection, self.blocks)
        self.assertTrue(fresh)
        self.assertEqual(len(stored), 24)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM sampled_block").fetchone()[0], 24)

    def test_resume_reuses_stored_blocks_and_ignores_a_different_schedule(self):
        B8B.store_blocks(self.connection, self.blocks)
        moved = [dict(b, start_slot=b["start_slot"] + 999_999) for b in self.blocks]
        stored, fresh = B8B.store_blocks(self.connection, moved)
        self.assertFalse(fresh, "a resumed run must not re-freeze the schedule")
        self.assertEqual([b["start_slot"] for b in stored],
                         [b["start_slot"] for b in self.blocks],
                         "the stored schedule must win - otherwise the sample silently moves")

    def test_metadata_records_enough_to_re_derive_the_sample(self):
        meta = B8B.freeze_metadata(433894233, 434097833, 1784463582, "idlhash", "configured")
        for key in ("freeze_sha256", "stride", "modulus", "block_minutes",
                    "window_start_slot", "window_end_slot_inclusive", "window_start_time",
                    "idl_sha256", "program_id"):
            self.assertIn(key, meta, f"artifact must be self-describing: missing {key}")
        self.assertEqual(meta["freeze_sha256"], B8B.FREEZE_SHA256)


class SchemaTests(unittest.TestCase):
    def test_reuses_the_b8a_tables_so_the_cohorts_are_comparable(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "schema.sqlite"
        connection = B8B.open_database(str(path))
        self.addCleanup(connection.close)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertLessEqual({"metadata", "slot_scan", "create_event", "decode_error",
                              "sampled_block"}, tables)


class CrashDurabilityTests(unittest.TestCase):
    """`partial completion is FAIL` only works if the run is resumable rather than restartable.

    That rests entirely on `b7d_create_enumerator.store_result` wrapping its writes in
    `with connection:`, which commits per slot. There is exactly **one** explicit `commit()` in that
    module and it is in `initialize_metadata`, so the per-slot durability is easy to remove by
    accident while every other test still passes. This test fails if that happens: without the
    context manager a hard kill loses the entire scan, and a restart would silently redraw the
    sample rather than resume it.
    """

    def test_a_hard_kill_keeps_every_slot_already_stored(self):
        import subprocess
        import sys
        import textwrap

        path = pathlib.Path(tempfile.mkdtemp()) / "crash.sqlite"
        writer = textwrap.dedent(f"""
            import importlib.util, os
            spec = importlib.util.spec_from_file_location(
                'b7d', {str(ROOT / 'scripts' / 'b7d_create_enumerator.py')!r})
            b7d = importlib.util.module_from_spec(spec); spec.loader.exec_module(b7d)
            connection = b7d.connect_database({str(path)!r})
            b7d.initialize_metadata(connection, {{'k': 'v'}})
            for i in range(300):
                b7d.store_result(connection, 1000 + i, 'skipped', None, 'x',
                                 b'\\0' * 8, None, {{}}, set())
            os._exit(9)                      # hard kill: no close, no flush, no cleanup
        """)
        subprocess.run([sys.executable, "-c", writer], cwd=str(ROOT), check=False,
                       capture_output=True)
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.addCleanup(connection.close)
        survived = connection.execute("SELECT COUNT(*) FROM slot_scan").fetchone()[0]
        self.assertEqual(survived, 300,
                         "store_result must commit per slot; a crash losing stored slots turns "
                         "'resume' into 'redraw the sample'")


_census_spec = importlib.util.spec_from_file_location(
    "b8b_census", str(ROOT / "scripts" / "b8b_census.py"))
CENSUS = importlib.util.module_from_spec(_census_spec)
_census_spec.loader.exec_module(CENSUS)


class ActorGroupingTests(unittest.TestCase):
    """`creator ∪ user` is the frozen split key. Grouping by `creator` alone silently splits one
    actor operating under two pubkeys, which is the leakage the key exists to prevent."""

    def test_bridged_pubkeys_collapse_into_one_actor(self):
        # A launches twice as itself; B launches once as itself and once with A as `user`.
        rows = [("A", "A"), ("A", "A"), ("B", "B"), ("B", "A")]
        self.assertEqual(len(set(CENSUS.actor_groups(rows))), 1,
                         "creator-only grouping would report 2 actors here")

    def test_unbridged_actors_stay_separate(self):
        rows = [("A", "A"), ("B", "B"), ("C", "C")]
        self.assertEqual(len(set(CENSUS.actor_groups(rows))), 3)

    def test_transitive_bridging(self):
        """A-B and B-C must put A and C together even though no row names both."""
        rows = [("A", "B"), ("B", "C"), ("D", "D")]
        groups = CENSUS.actor_groups(rows)
        self.assertEqual(groups[0], groups[1])
        self.assertNotEqual(groups[0], groups[2])

    def test_share_from_repeat_actor_is_not_the_surplus(self):
        """B8a's census quoted the surplus as if it were the exposed share. Both are reported."""
        rows = [("A", "A"), ("A", "A"), ("B", "B"), ("C", "C")]
        result = CENSUS.leakage(rows, "synthetic")
        self.assertEqual(result["members_from_a_repeat_actor"], 2)
        self.assertAlmostEqual(result["share_from_repeat_actor"], 0.5)
        self.assertEqual(result["surplus_beyond_one_each"], 1)
        self.assertAlmostEqual(result["share_surplus"], 0.25)
        self.assertNotEqual(result["share_from_repeat_actor"], result["share_surplus"])

    def test_empty_population_does_not_divide_by_zero(self):
        result = CENSUS.leakage([], "empty")
        self.assertEqual(result["n"], 0)
        self.assertEqual(result["share_from_repeat_actor"], 0.0)


if __name__ == "__main__":
    unittest.main()
