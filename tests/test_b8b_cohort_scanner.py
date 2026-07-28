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
        result = CENSUS.leakage(rows, "synthetic", CENSUS.component_map(rows))
        self.assertEqual(result["members_from_a_repeat_actor"], 2)
        self.assertAlmostEqual(result["share_from_repeat_actor"], 0.5)
        self.assertEqual(result["surplus_beyond_one_each"], 1)
        self.assertAlmostEqual(result["share_surplus"], 0.25)
        self.assertNotEqual(result["share_from_repeat_actor"], result["share_surplus"])

    def test_empty_population_does_not_divide_by_zero(self):
        result = CENSUS.leakage([], "empty", {})
        self.assertEqual(result["n"], 0)
        self.assertEqual(result["share_from_repeat_actor"], 0.0)

    def test_two_creators_bridged_only_by_a_shared_user(self):
        """Neither `X` is ever a creator, so a creator-only implementation passes this by accident
        and a bridge-counting one misses it. A and B are one actor via X."""
        self.assertEqual(len(set(CENSUS.actor_groups([("A", "X"), ("B", "X")]))), 1)


class SubsetLeakageTests(unittest.TestCase):
    """F3 (Seq 129): leakage over a subset must use the FULL cohort's actor graph.

    Rebuilding components from the filtered rows loses identity links proven by excluded rows, and
    it fails in the anti-conservative direction — under-reporting leakage in the very measure that
    exists to stop an actor landing on both sides of a split. B8a had five creators launching both
    Mayhem and non-Mayhem, so this is a live case, not a constructed one.
    """

    # (A,B) is Mayhem and excluded; it is also the only proof that A and B are one actor.
    ALL = [("A", "B"), ("A", "A"), ("B", "B")]
    TRADABLE = [("A", "A"), ("B", "B")]

    def test_subset_leakage_uses_links_proven_by_excluded_rows(self):
        component_of = CENSUS.component_map(self.ALL)
        result = CENSUS.leakage(self.TRADABLE, "tradable", component_of)
        self.assertEqual(result["distinct_actor_groups"], 1,
                         "A and B are one actor; the Mayhem row proves it")
        self.assertEqual(result["members_from_a_repeat_actor"], 2)
        self.assertAlmostEqual(result["share_from_repeat_actor"], 1.0)

    def test_rebuilding_from_the_subset_would_have_reported_zero(self):
        """Pins the magnitude of the old defect so the regression is unmistakable."""
        subset_only = CENSUS.leakage(self.TRADABLE, "tradable", CENSUS.component_map(self.TRADABLE))
        self.assertAlmostEqual(subset_only["share_from_repeat_actor"], 0.0)
        full = CENSUS.leakage(self.TRADABLE, "tradable", CENSUS.component_map(self.ALL))
        self.assertAlmostEqual(full["share_from_repeat_actor"], 1.0)

    def test_an_incomplete_component_map_is_refused_rather_than_guessed(self):
        """No default for `component_of`: silently rebuilding from the subset is the defect."""
        with self.assertRaises(ValueError) as ctx:
            CENSUS.leakage(self.TRADABLE, "tradable", CENSUS.component_map([("Z", "Z")]))
        self.assertIn("full cohort", str(ctx.exception))

    def test_leakage_requires_the_component_map_argument(self):
        with self.assertRaises(TypeError):
            CENSUS.leakage(self.TRADABLE, "tradable")

    def test_main_builds_the_map_from_the_full_cohort(self):
        """Anti-vacuity, and it is not hypothetical: the fix lives at a *call site*, so the unit
        tests above all still pass if `main()` is changed back to `component_map(tradable)`.
        Verified by mutation — that regression was invisible until this test existed.

        Fixture: one Mayhem row proving `A` and `B` are one actor, plus one tradable launch from
        each. Correct tradable leakage is 100%; rebuilding from the subset reports 0%.
        """
        import json
        import subprocess
        import sys
        path = pathlib.Path(tempfile.mkdtemp()) / "bridge.sqlite"
        connection = B8B.open_database(str(path))
        for hour in range(24):
            start = 1000 + hour * 10
            connection.execute("INSERT INTO sampled_block VALUES (?,?,?,?,0,0)",
                               (hour, (27 * hour) % 59, start, start + 1))
            connection.execute("INSERT INTO slot_scan(slot,status,error,scanned_at_unix) "
                               "VALUES (?,'retrieved',NULL,0)", (start,))
        rows = [("A", "B", 1), ("A", "A", 0), ("B", "B", 0)]
        for index, (creator, user, mayhem) in enumerate(rows):
            connection.execute(
                "INSERT INTO create_event(slot,transaction_index,outer_instruction_index,"
                "inner_instruction_index,signature,mint,bonding_curve,creator,user,"
                "is_mayhem_mode,is_cashback_enabled,quote_mint,fields_json,"
                "event_payload_base64) VALUES (?,?,0,0,?,?,?,?,?,?,0,?,'{}','')",
                (1000, index, f"SIG{index}", f"MINT{index}", f"CURVE{index}",
                 creator, user, mayhem, CENSUS.SOL_SENTINEL))
        connection.commit()
        connection.close()

        out = path.with_suffix(".json")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "b8b_census.py"),
                        "--database", str(path), "--json", str(out)],
                       capture_output=True, text=True, cwd=str(ROOT))
        report = json.loads(out.read_text())
        tradable = next(r for r in report["leakage"] if r["population"].startswith("tradable"))
        self.assertEqual(tradable["n"], 2)
        self.assertEqual(tradable["distinct_actor_groups"], 1,
                         "main() must build the actor graph from the FULL cohort; rebuilding it "
                         "from the tradable subset loses the link the Mayhem row proves")
        self.assertAlmostEqual(tradable["share_from_repeat_actor"], 1.0)


class CensusVerdictTests(unittest.TestCase):
    """F1/F2 (Seq 129): the verdict must enforce every condition the output calls a "must"."""

    OK = dict(blocks=[{"hour": h} for h in range(24)], sampled={1, 2, 3}, missing=set(),
              unverified=0, decode_errors=0, create_events=10, distinct_mints=10)

    def test_a_clean_artifact_passes(self):
        self.assertEqual(CENSUS.census_failures(**self.OK), [])

    def test_an_empty_artifact_fails_rather_than_passing_vacuously(self):
        failures = CENSUS.census_failures(**dict(self.OK, blocks=[], sampled=set(),
                                                 create_events=0, distinct_mints=0))
        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(any("24 hourly strata" in f for f in failures))
        self.assertTrue(any("zero sampled slots" in f for f in failures))

    def test_a_partial_schedule_fails(self):
        self.assertTrue(any("hourly strata" in f for f in
                            CENSUS.census_failures(**dict(self.OK, blocks=[{"hour": 0}] * 3))))

    def test_decode_errors_fail_the_census_as_they_fail_the_scanner(self):
        failures = CENSUS.census_failures(**dict(self.OK, decode_errors=1))
        self.assertTrue(any("C4" in f for f in failures),
                        "an undecodable CreateEvent breaks exhaustiveness")

    def test_duplicate_mints_fail(self):
        self.assertTrue(any("duplicate membership" in f for f in
                            CENSUS.census_failures(**dict(self.OK, distinct_mints=9))))

    def test_missing_slots_and_unverified_skips_still_fail(self):
        self.assertTrue(CENSUS.census_failures(**dict(self.OK, missing={7})))
        self.assertTrue(CENSUS.census_failures(**dict(self.OK, unverified=1)))

    def test_main_actually_uses_the_gate(self):
        """Anti-vacuity: the unit tests above are worthless if main() gates on something else.

        Runs the real script against an empty temp database and requires a non-zero exit.
        """
        import subprocess
        import sys
        path = pathlib.Path(tempfile.mkdtemp()) / "empty.sqlite"
        connection = B8B.open_database(str(path))
        connection.commit()
        connection.close()
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "b8b_census.py"), "--database", str(path)],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 1, result.stdout[-2000:])
        self.assertIn("CENSUS VERDICT: FAIL", result.stdout)


class BlockWidthTests(unittest.TestCase):
    """F6 (Seq 132): `resolve_blocks` refuses `after <= begin`, but it is NEVER CALLED on a resume.

    The resume path reads `sampled_block` straight from the database, so `assert_complete_schedule`
    is the only thing standing between a corrupt stored schedule and the run. A zero-width block
    contributes no slots, so its hour disappears from `sampled`, nothing is reported "missing", and
    a 23-stratum run reports COMPLETE — the same vacuity shape as F1.
    """

    def blocks(self, **override):
        out = [{"hour": h, "offset_minutes": (27 * h) % 59,
                "start_slot": 1000 + h * 100, "end_slot_exclusive": 1000 + h * 100 + 50,
                "start_time": 0, "end_time": 0} for h in range(24)]
        for hour, changes in override.items():
            out[int(hour)].update(changes)
        return out

    def test_a_healthy_schedule_passes(self):
        B8B.assert_complete_schedule(self.blocks(), "test")

    def test_a_zero_width_block_fails_closed(self):
        blocks = self.blocks()
        blocks[7]["end_slot_exclusive"] = blocks[7]["start_slot"]
        with self.assertRaises(SystemExit) as ctx:
            B8B.assert_complete_schedule(blocks, "stored")
        self.assertIn("non-positive block width", str(ctx.exception))

    def test_an_inverted_block_fails_closed(self):
        blocks = self.blocks()
        blocks[3]["end_slot_exclusive"] = blocks[3]["start_slot"] - 5
        with self.assertRaises(SystemExit):
            B8B.assert_complete_schedule(blocks, "stored")

    def test_the_dropped_stratum_would_otherwise_be_invisible(self):
        """Documents why this needs its own check: no other invariant notices."""
        blocks = self.blocks()
        blocks[7]["end_slot_exclusive"] = blocks[7]["start_slot"]
        sampled = [s for b in blocks
                   for s in range(b["start_slot"], b["end_slot_exclusive"])]
        self.assertEqual(len(blocks), 24, "block count still looks right")
        self.assertEqual(sorted(b["hour"] for b in blocks), list(range(24)),
                         "hour coverage still looks right")
        overlaps = [(a, b) for a, b in zip(blocks, blocks[1:])
                    if a["end_slot_exclusive"] > b["start_slot"]]
        self.assertEqual(overlaps, [], "the overlap check still passes")
        self.assertEqual(len(sampled), 23 * 50, "yet one whole stratum contributes nothing")


class ObservationPowerTests(unittest.TestCase):
    """F7 (Seq 132): a stratum that was observed and yielded nothing is NOT the same as a stratum
    that was never observed, and the previous `creates` column could not tell them apart.

    Seq 131 decided — correctly — that a zero-launch stratum must stay a NOTE, because failing on
    it conflates "we looked and found nothing" with "we did not look". That reasoning only covers
    the first case. Zero *retrieved* slots is the second case and is a genuine fault.
    """

    def test_zero_retrieved_slots_fails(self):
        failures = CENSUS.census_failures(
            blocks=[{"hour": h} for h in range(24)], sampled={1}, missing=set(), unverified=0,
            decode_errors=0, create_events=1, distinct_mints=1, zero_observed=[7])
        self.assertTrue(any("zero retrieved slots" in f for f in failures), failures)

    def test_observed_but_empty_strata_do_not_fail(self):
        failures = CENSUS.census_failures(
            blocks=[{"hour": h} for h in range(24)], sampled={1}, missing=set(), unverified=0,
            decode_errors=0, create_events=1, distinct_mints=1, zero_observed=[])
        self.assertEqual(failures, [])

    def test_main_distinguishes_the_two_cases_end_to_end(self):
        """Call-site test, per the F3 lesson: the unit tests above all pass even if `main()` never
        computes `zero_observed`. Fixture: hour 5 has a retrieved slot and no launch (NOTE), hour 9
        has only a skipped slot and therefore no observation power (FAIL)."""
        import json
        import subprocess
        import sys
        path = pathlib.Path(tempfile.mkdtemp()) / "power.sqlite"
        connection = B8B.open_database(str(path))
        for hour in range(24):
            start = 1000 + hour * 10
            connection.execute("INSERT INTO sampled_block VALUES (?,?,?,?,0,0)",
                               (hour, (27 * hour) % 59, start, start + 1))
            status = "skipped" if hour == 9 else "retrieved"
            connection.execute("INSERT INTO slot_scan(slot,status,error,scanned_at_unix) "
                               "VALUES (?,?,?,0)",
                               (start, status,
                                "absence verified by getBlocks" if status == "skipped" else None))
            if hour not in (5, 9):                       # hour 5 observed but empty
                connection.execute(
                    "INSERT INTO create_event(slot,transaction_index,outer_instruction_index,"
                    "inner_instruction_index,signature,mint,bonding_curve,creator,user,"
                    "is_mayhem_mode,is_cashback_enabled,quote_mint,fields_json,"
                    "event_payload_base64) VALUES (?,0,0,0,?,?,?,?,?,0,0,?,'{}','')",
                    (start, f"SIG{hour}", f"MINT{hour}", f"CURVE{hour}",
                     f"C{hour}", f"C{hour}", CENSUS.SOL_SENTINEL))
        connection.commit()
        connection.close()

        out = path.with_suffix(".json")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "b8b_census.py"),
                        "--database", str(path), "--json", str(out)],
                       capture_output=True, text=True, cwd=str(ROOT))
        report = json.loads(out.read_text())
        self.assertEqual(report["strata_zero_launch"], [5],
                         "an observed-but-empty stratum must be reported as a NOTE, not a fault")
        self.assertEqual(report["strata_zero_observed"], [9],
                         "a stratum with no retrieved slots must be identified")
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(any("zero retrieved slots" in f for f in report["failures"]),
                        report["failures"])


class AchievedPrecisionTests(unittest.TestCase):
    """Owner decision A: report the precision the realised `n` supports; claim nothing tighter."""

    def test_the_projected_n_misses_the_bar_and_says_so(self):
        result = CENSUS.achieved_precision(1300)
        self.assertFalse(result["meets_bar_at_1pct"])
        self.assertAlmostEqual(result["half_widths"]["0.01"], 0.00541, places=4)

    def test_the_exact_requirement_is_reported(self):
        self.assertEqual(CENSUS.achieved_precision(1300)["n_required"], 1522)

    def test_the_bar_still_holds_for_rarer_regimes(self):
        """The miss is a narrow band around 1%, not a blanket failure - worth not overstating."""
        self.assertGreater(CENSUS.achieved_precision(1300)["max_p"], 0.008)
        self.assertLess(CENSUS.achieved_precision(1300)["max_p"], 0.010)

    def test_a_sufficient_n_passes(self):
        self.assertTrue(CENSUS.achieved_precision(1715)["meets_bar_at_1pct"])
        self.assertTrue(CENSUS.achieved_precision(1522)["meets_bar_at_1pct"])

    def test_zero_n_does_not_divide_by_zero(self):
        result = CENSUS.achieved_precision(0)
        self.assertFalse(result["meets_bar_at_1pct"])
        self.assertEqual(result["max_p"], 0.0)


class ScheduleCompletenessTests(unittest.TestCase):
    """F4 (Seq 129): a partial stored schedule was reused as the sample with no complaint."""

    def blocks(self, count=24):
        return [{"hour": h, "offset_minutes": (27 * h) % 59,
                 "start_slot": 1000 + h * 100, "end_slot_exclusive": 1000 + h * 100 + 50,
                 "start_time": 0, "end_time": 0} for h in range(count)]

    def test_a_full_schedule_passes(self):
        B8B.assert_complete_schedule(self.blocks(), "test")

    def test_a_truncated_schedule_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            B8B.assert_complete_schedule(self.blocks(3), "stored")
        self.assertIn("FAIL CLOSED", str(ctx.exception))

    def test_a_duplicated_hour_fails_closed(self):
        blocks = self.blocks()
        blocks[5]["hour"] = 4
        with self.assertRaises(SystemExit):
            B8B.assert_complete_schedule(blocks, "stored")

    def test_an_offset_off_the_frozen_rule_fails_closed(self):
        blocks = self.blocks()
        blocks[7]["offset_minutes"] += 1
        with self.assertRaises(SystemExit) as ctx:
            B8B.assert_complete_schedule(blocks, "stored")
        self.assertIn("frozen rule", str(ctx.exception))

    def test_store_blocks_refuses_to_reuse_a_truncated_stored_schedule(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "partial.sqlite"
        connection = B8B.open_database(str(path))
        self.addCleanup(connection.close)
        for block in self.blocks(3):
            connection.execute(
                "INSERT INTO sampled_block VALUES (?,?,?,?,?,?)",
                (block["hour"], block["offset_minutes"], block["start_slot"],
                 block["end_slot_exclusive"], 0, 0))
        connection.commit()
        with self.assertRaises(SystemExit) as ctx:
            B8B.store_blocks(connection, None)
        self.assertIn("FAIL CLOSED", str(ctx.exception))


class WindowStartTimeTests(unittest.TestCase):
    """F5 (Seq 129): the declared start time defines all 24 boundaries and was never checked.

    A wrong value shifts every block coherently, so nothing downstream looks odd — the sample is
    simply not the one the freeze describes.
    """

    BASE, T0 = 1000, 500_000

    def setUp(self):
        chain = {s: self.T0 + (s - self.BASE) * 2 for s in range(self.BASE, self.BASE + 5000)}
        self._real = B8B._get_block_time
        B8B._get_block_time = lambda url, slot, retries: chain.get(slot)
        self.addCleanup(lambda: setattr(B8B, "_get_block_time", self._real))

    def test_a_correct_start_time_is_accepted(self):
        found = B8B.verify_window_start_time("url", self.BASE, self.BASE + 4999, self.T0, 1)
        self.assertEqual(found, self.BASE)

    def test_a_start_time_a_few_slots_off_is_tolerated(self):
        B8B.verify_window_start_time("url", self.BASE, self.BASE + 4999, self.T0 + 20, 1)

    def test_a_start_time_minutes_off_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            B8B.verify_window_start_time("url", self.BASE, self.BASE + 4999, self.T0 + 600, 1)
        self.assertIn("moves the entire sample", str(ctx.exception))

    def test_a_start_time_outside_the_window_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            B8B.verify_window_start_time("url", self.BASE, self.BASE + 4999, self.T0 + 10 ** 6, 1)
        self.assertIn("not in this window", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
