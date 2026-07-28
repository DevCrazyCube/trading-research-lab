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
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "b8b", str(ROOT / "scripts" / "b8b_cohort_scanner.py"))
B8B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B8B)

ANCHOR = 500_000


def schedule_blocks(count=24, anchor=ANCHOR, width=580):
    """A schedule as `resolve_blocks` would actually produce one.

    One shared builder because three fixtures previously carried placeholder times (`0`/`0`, or a
    span with no offset term). Those are not schedules the scanner can emit, and a fixture that
    production cannot produce is how a test ends up pinning nothing - the Seq-67 lesson. Every
    field here satisfies the frozen grid, so a test that fails does so for its own reason.
    """
    offsets = [(B8B.STRIDE * h) % B8B.MODULUS for h in range(count)]
    return [{"hour": h, "offset_minutes": offsets[h],
             "start_slot": 1000 + h * 1000, "end_slot_exclusive": 1000 + h * 1000 + width,
             "start_time": anchor + h * 3600 + offsets[h] * 60,
             "end_time": anchor + h * 3600 + offsets[h] * 60 + B8B.BLOCK_MINUTES * 60}
            for h in range(count)]


def census_template():
    """The census TEMPLATE — a file of its own, not the filled output.

    Reading the output as its own input broke four tests the moment the real fill ran: a filled
    document has no placeholders, so those tests silently stopped testing substitution. Reading it
    from `git show HEAD:` had the same defect one commit later. The template is now a separate
    tracked file, so it survives its own output.
    """
    return (ROOT / "research" / "B8B_COHORT_CENSUS.template.md").read_text()


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
        self.blocks = schedule_blocks()

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
              unverified=0, decode_errors=0, create_events=10, distinct_mints=10,
              zero_observed=(), members_outside_blocks=0)

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

    def test_members_outside_the_sampled_blocks_fail(self):
        """F12 (Seq 139): the mirror of `missing`.

        `missing` catches sampled slots never scanned; this catches members never sampled. The
        launch window IS the union of the 24 blocks, so a launch outside all of them is not a
        member — and every downstream figure is computed over `create_event`.
        """
        failures = CENSUS.census_failures(**dict(self.OK, members_outside_blocks=1))
        self.assertTrue(any("outside every sampled block" in f for f in failures), failures)

    def test_every_gate_argument_is_required(self):
        """Per the F11 rule: an optional argument turns a dropped call-site argument into a silent
        no-op. Five call-site vacuities in this project; required parameters remove the shape."""
        for omit in ("zero_observed", "members_outside_blocks", "decode_errors", "distinct_mints"):
            arguments = {k: v for k, v in self.OK.items() if k != omit}
            with self.assertRaises(TypeError, msg=f"{omit} must be required"):
                CENSUS.census_failures(**arguments)

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
        out = schedule_blocks()
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
        # Derived from the fixture rather than hardcoded, so the assertion survives a change of
        # fixture geometry instead of silently becoming an arithmetic identity about it.
        intact = self.blocks()
        width = intact[7]["end_slot_exclusive"] - intact[7]["start_slot"]
        expected_full = sum(b["end_slot_exclusive"] - b["start_slot"] for b in intact)
        self.assertEqual(len(sampled), expected_full - width,
                         "yet one whole stratum contributes nothing")


class StoredTimeValidationTests(unittest.TestCase):
    """F8 (Seq 133): the stored *times* define each block; nothing validated them.

    `start_slot`/`end_slot_exclusive` are only the resolution of those times against the chain, so
    a schedule with correct slot bounds and wrong times is not the sample the freeze describes. A
    1-second span and a start six hours off the grid both passed every earlier check.
    """

    def test_a_healthy_schedule_passes(self):
        B8B.assert_complete_schedule(schedule_blocks(), "test")

    def test_the_check_is_self_anchoring_so_any_real_window_passes(self):
        """No anchor argument: offset(0)=0, so hour 0's start_time IS the window anchor."""
        for anchor in (0, 500_000, 1784463582):
            B8B.assert_complete_schedule(schedule_blocks(anchor=anchor), f"anchor {anchor}")

    def test_a_wrong_time_span_fails_closed(self):
        blocks = schedule_blocks()
        blocks[7]["end_time"] = blocks[7]["start_time"] + 1
        with self.assertRaises(SystemExit) as ctx:
            B8B.assert_complete_schedule(blocks, "stored")
        self.assertIn("time span is not 240s", str(ctx.exception))

    def test_a_span_wrong_by_one_second_fails_closed(self):
        """Exact invariant, so it is checked exactly - no tolerance to erode later."""
        blocks = schedule_blocks()
        blocks[0]["end_time"] += 1
        with self.assertRaises(SystemExit):
            B8B.assert_complete_schedule(blocks, "stored")

    def test_a_start_time_off_the_frozen_grid_fails_closed(self):
        for shift in (60, 3600, 21600):
            blocks = schedule_blocks()
            blocks[7]["start_time"] += shift
            blocks[7]["end_time"] += shift
            with self.assertRaises(SystemExit) as ctx:
                B8B.assert_complete_schedule(blocks, "stored")
            self.assertIn("off the frozen grid", str(ctx.exception), f"shift {shift}")

    def test_times_must_match_the_offset_the_same_row_declares(self):
        """A row whose offset column and start_time disagree is internally inconsistent."""
        blocks = schedule_blocks()
        blocks[5]["start_time"] += 60
        blocks[5]["end_time"] += 60
        with self.assertRaises(SystemExit):
            B8B.assert_complete_schedule(blocks, "stored")

    def test_a_coherent_shift_of_every_block_is_deliberately_out_of_scope(self):
        """Documents the boundary rather than implying coverage.

        Shifting all 24 blocks equally is still a valid grid, so this check cannot see it - that
        is `verify_window_start_time`'s job on a fresh resolve, and the metadata mismatch check's
        job on a resume. Asserting it here would be claiming a guarantee this function does not
        provide.
        """
        B8B.assert_complete_schedule(schedule_blocks(anchor=ANCHOR + 86_400), "shifted")

    def test_a_one_slot_wide_block_is_NOT_caught_and_that_is_recorded(self):
        """Also a boundary: slot bounds cannot be re-verified without RPC.

        A stratum reduced to one slot keeps a valid grid and a positive width, so it survives. It
        would need chain access to detect, and F7's zero-retrieved gate does not fire on 1. Pinned
        so the limit is visible rather than assumed away.
        """
        blocks = schedule_blocks()
        blocks[7]["end_slot_exclusive"] = blocks[7]["start_slot"] + 1
        B8B.assert_complete_schedule(blocks, "stored")      # passes, knowingly

class ScheduleWindowTieTests(unittest.TestCase):
    """F9 (Seq 135): a coherently shifted schedule passes every other check.

    Seq 134 pinned the shift as a deliberate non-guarantee of `assert_complete_schedule` and named
    the metadata mismatch check as the thing that would catch it on a resume. Measured, it does
    not: the schedule and the metadata are separate stores, so shifting every `start_time` and
    leaving `metadata` alone passes both. A resume would sample 24 blocks from the wrong part of
    the day, satisfy every invariant, and report COMPLETE.
    """

    def test_a_matching_anchor_passes(self):
        B8B.assert_schedule_anchor(schedule_blocks(anchor=ANCHOR), ANCHOR, "test")

    def test_a_coherently_shifted_schedule_is_refused(self):
        blocks = schedule_blocks(anchor=ANCHOR + 7200)          # every block 2h later
        with self.assertRaises(SystemExit) as ctx:
            B8B.assert_schedule_anchor(blocks, ANCHOR, "stored")
        self.assertIn("anchored at", str(ctx.exception))

    def test_a_one_second_shift_is_refused_there_is_no_tolerance(self):
        """Both sides are recorded integers, so this is an equality, not a measurement."""
        with self.assertRaises(SystemExit):
            B8B.assert_schedule_anchor(schedule_blocks(anchor=ANCHOR + 1), ANCHOR, "stored")

    def test_the_shift_really_does_pass_every_other_check(self):
        """Documents why F9 needs to exist rather than being folded into an existing check."""
        blocks = schedule_blocks(anchor=ANCHOR + 7200)
        B8B.assert_complete_schedule(blocks, "internally coherent")     # passes, correctly
        self.assertEqual(len(blocks), 24)
        self.assertEqual(sorted(b["hour"] for b in blocks), list(range(24)))

    def test_empty_schedule_is_left_to_the_other_checks(self):
        B8B.assert_schedule_anchor([], ANCHOR, "empty")


    def test_main_actually_calls_the_tie_check(self):
        """Call-site test. Every assertion above passes even if `main()` never calls the function -
        verified by mutation: removing the call site survived the whole unit suite. This is the
        third time this project has hit call-site vacuity (Seq 100, Seq 109, Seq 131), and I hit it
        again one entry after naming it.

        A stored schedule takes the resume path, and the tie check runs before any RPC, so this
        makes no network call.
        """
        import subprocess
        import sys
        path = pathlib.Path(tempfile.mkdtemp()) / "shifted.sqlite"
        connection = B8B.open_database(str(path))
        declared = 1784463582
        # Metadata must match what the subprocess will compute, or `initialize_metadata` raises
        # first and the tie check is never reached. The real IDL hash; `public-mainnet` because the
        # test environment sets no SOLANA_RPC_URL.
        import hashlib
        idl_sha = hashlib.sha256((ROOT / "research" / "pump_idl_9c82f61.json").read_bytes()).hexdigest()
        B8B.B7D.initialize_metadata(connection, B8B.freeze_metadata(
            433894233, 434097833, declared, idl_sha, "public-mainnet"))
        offsets = B8B.offsets()
        for hour in range(24):                       # every block shifted 2h from `declared`
            begin = declared + 7200 + 3600 * hour + 60 * offsets[hour]
            connection.execute("INSERT INTO sampled_block VALUES (?,?,?,?,?,?)",
                               (hour, offsets[hour], 433894233 + hour * 1000,
                                433894233 + hour * 1000 + 560, begin, begin + 240))
        connection.commit()
        connection.close()

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "b8b_cohort_scanner.py"),
             "--database", str(path), "--window-start-time", str(declared), "--resolve-only"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertNotEqual(result.returncode, 0,
                            "main() must refuse a schedule anchored outside the declared window")
        self.assertIn("anchored at", result.stdout + result.stderr)


class CensusFillerTests(unittest.TestCase):
    """The filler exists so the census's numbers are not retyped. Its refusals are the point."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "b8b_fill", str(ROOT / "scripts" / "b8b_fill_census.py"))
        self.FILL = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.FILL)

    def report(self, **override):
        base = {
            "verdict": "COMPLETE", "failures": [],
            "completeness": {"blocks": 24, "sampled": 13533, "missing": 0, "skips_unverified": 0,
                             "decode_errors": 0, "members_outside_blocks": 0,
                             "status": {"retrieved": 13400, "skipped": 133}},
            "cohort": {"create_events": 1700, "distinct_mints": 1700,
                       "members_outside_blocks": 0},
            "precision": {"half_widths": {"0.01": 0.00473, "0.033": 0.0085},
                          "max_p_meeting_bar": 0.011, "max_p": 0.011, "bar": 0.005,
                          "n_required": 1522, "meets_bar_at_1pct": True},
            "per_hour": [{"hour": h, "offset": (27 * h) % 59, "creates": 70,
                          "retrieved_slots": 560, "skipped_slots": 2} for h in range(24)],
            "quote_regimes": {self.FILL.SOL_SENTINEL: 1650, self.FILL.USDC: 50},
            "is_mayhem_mode": {"0": 1400, "1": 300},
            "is_cashback_enabled": {"0": 900, "1": 800},
            "leakage": [{"population": "all", "n": 1700, "distinct_actor_groups": 1000,
                         "repeat_actor_groups": 300, "members_from_a_repeat_actor": 1000,
                         "share_from_repeat_actor": 0.588, "surplus_beyond_one_each": 700,
                         "share_surplus": 0.412, "largest_actor_group": 12}],
            "metadata": dict(self.METADATA),
        }
        base.update(override)
        return base

    # The artifact's own metadata table, copied into the report by `b8b_census.py`. C1 (Seq 152)
    # compares the two, so a fixture must build an artifact that genuinely matches its report -
    # a stub file would only ever exercise the refusal path.
    METADATA = {"schema_version": "b8b-v1", "window_start_slot": "433894233",
                "window_end_slot_inclusive": "434097833", "window_start_time": "1784463582",
                "stride": "27", "modulus": "59", "block_minutes": "4"}

    def artifact(self, directory, metadata=None):
        """A real SQLite artifact whose metadata matches the report unless told otherwise."""
        path = pathlib.Path(directory) / "art.sqlite"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany("INSERT INTO metadata VALUES (?,?)",
                               (metadata or self.METADATA).items())
        connection.commit()
        connection.close()
        return path

    def test_a_complete_report_fills_every_placeholder(self):
        import re
        text = census_template()
        filled = self.FILL.values(self.report(), "abc123")
        tokens = set(re.findall(r"«([^»]+)»", text))
        self.assertEqual(tokens - set(filled), set(),
                         "every placeholder must map to a measured value")

    def test_a_short_per_hour_list_is_refused(self):
        """Found by mutation: a report claiming COMPLETE with 5 strata rendered a 5-row table
        under prose describing 24, and nothing failed."""
        import json
        import subprocess
        import sys
        report = self.report()
        report["per_hour"] = report["per_hour"][:5]
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "r.json").write_text(json.dumps(report))
        (tmp / "t.md").write_text(census_template())
        self.artifact(tmp)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "b8b_fill_census.py"),
             "--json", str(tmp / "r.json"), "--census", str(tmp / "c.md"),
             "--database", str(tmp / "art.sqlite")],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("per-hour rows", result.stdout + result.stderr)

    def fill(self, tmp, **extra):
        import subprocess
        import sys
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "b8b_fill_census.py"),
             "--json", str(tmp / "r.json"), "--template", str(tmp / "t.md"),
             "--census", str(tmp / "c.md"),
             "--database", str(extra.get("database", tmp / "art.sqlite"))],
            capture_output=True, text=True, cwd=str(ROOT))

    def prepared(self):
        import json
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "r.json").write_text(json.dumps(self.report()))
        (tmp / "t.md").write_text(census_template())
        self.artifact(tmp)
        return tmp

    def test_the_artifact_hash_is_computed_not_supplied(self):
        """B1 (Seq 150): the script exists so numbers stop being retyped, then required a
        64-character hash to be typed by hand and wrote it in unchecked. Now derived."""
        import hashlib
        tmp = self.prepared()
        result = self.fill(tmp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        expected = hashlib.sha256((tmp / "art.sqlite").read_bytes()).hexdigest()
        self.assertIn(expected, (tmp / "c.md").read_text())

    def test_there_is_no_way_to_supply_a_hash_by_hand(self):
        import subprocess
        import sys
        tmp = self.prepared()
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "b8b_fill_census.py"),
             "--json", str(tmp / "r.json"), "--census", str(tmp / "c.md"),
             "--artifact-sha", "not-a-hash-at-all"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertNotEqual(result.returncode, 0, "--artifact-sha must not exist")

    def test_re_running_regenerates_rather_than_preserving_stale_output(self):
        """B2 (Seq 150) was: a second run found no placeholders, substituted nothing, printed
        success and left the previous numbers in place — which bites when you re-run to correct a
        bad fill. Splitting template from output removes that **by construction** rather than by
        refusal: each run reads the pristine template, so a stale output is overwritten, not kept.
        The property under test is therefore "the trap is gone", not "the refusal fires"."""
        tmp = self.prepared()
        self.assertEqual(self.fill(tmp).returncode, 0)
        first = (tmp / "c.md").read_text()
        (tmp / "c.md").write_text("STALE CONTENT FROM AN EARLIER FILL")
        self.assertEqual(self.fill(tmp).returncode, 0, "re-running must be legitimate")
        self.assertEqual((tmp / "c.md").read_text(), first,
                         "a stale output must be regenerated, never preserved")
        self.assertNotIn("STALE", (tmp / "c.md").read_text())

    def test_a_template_with_nothing_to_fill_is_refused(self):
        """The residual no-op case: if the template itself has been overwritten with output, there
        is nothing to substitute and reporting success would be meaningless."""
        tmp = self.prepared()
        (tmp / "t.md").write_text("# a document with no placeholders at all\n")
        result = self.fill(tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no placeholders", result.stdout + result.stderr)

    def test_a_missing_artifact_is_refused_with_a_reason(self):
        """Checking only the exit code passes for the wrong reason: an unguarded `read_bytes()`
        also exits non-zero, via an unhandled FileNotFoundError. Found by mutation - removing the
        guard left this test green. Pin the refusal, not merely the failure."""
        tmp = self.prepared()
        result = self.fill(tmp, database=tmp / "does_not_exist.sqlite")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REFUSING", output)
        self.assertNotIn("Traceback", output,
                         "a missing artifact must be a stated refusal, not a stack trace")

    def test_an_incomplete_verdict_has_no_bypass(self):
        """B3 (Seq 150): --allow-incomplete was hidden by argparse.SUPPRESS, so the docstring's
        primary refusal was false and invisible. Removed; tests use values() directly."""
        import json
        tmp = self.prepared()
        (tmp / "r.json").write_text(json.dumps(self.report(verdict="FAIL")))
        self.assertNotEqual(self.fill(tmp).returncode, 0)
        source = (ROOT / "scripts" / "b8b_fill_census.py").read_text()
        self.assertNotIn("allow_incomplete", source)
        self.assertNotIn("SUPPRESS", source)

    def test_a_missing_reported_value_refuses_rather_than_defaulting(self):
        """The filler read `members_outside_blocks` from the wrong section with a `, 0` default,
        so the census printed "0 members outside every sampled block" as a **default rather than a
        measurement**. It was the true value, which is exactly why it would never have been
        noticed — a provenance claim with nothing behind it, the same class as C1."""
        report = self.report()
        del report["cohort"]["members_outside_blocks"]
        with self.assertRaises(SystemExit) as ctx:
            self.FILL.values(report, "abc123")
        self.assertIn("members_outside_blocks", str(ctx.exception))

    def test_wilson_interval_is_asymmetric_and_shifted_up_at_small_p(self):
        """The whole reason it is reported instead of the Wald half-width."""
        low, high = self.FILL.wilson(1700, 0.01)
        self.assertLess(low, 1.0)
        self.assertGreater(high, 1.0)
        self.assertGreater(abs(high - 1.0), abs(1.0 - low), "Wilson must lean upward at p=1%")

    def test_zero_n_does_not_divide_by_zero(self):
        self.assertEqual(self.FILL.wilson(0), (0.0, 0.0))

    def test_an_unmapped_regime_is_flagged_not_silently_named(self):
        """A third quote mint must shout, not be quietly listed."""
        table = self.FILL.regime_table(self.report(quote_regimes={"SomeOtherMint": 5}))
        self.assertIn("OTHER", table)

    def test_tables_render_one_row_per_stratum(self):
        table = self.FILL.per_hour_table(self.report())
        self.assertEqual(len(table.splitlines()), 26, "header, separator, and 24 strata")


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
            decode_errors=0, create_events=1, distinct_mints=1, zero_observed=[7],
            members_outside_blocks=0)
        self.assertTrue(any("zero retrieved slots" in f for f in failures), failures)

    def test_observed_but_empty_strata_do_not_fail(self):
        failures = CENSUS.census_failures(
            blocks=[{"hour": h} for h in range(24)], sampled={1}, missing=set(), unverified=0,
            decode_errors=0, create_events=1, distinct_mints=1, zero_observed=[],
            members_outside_blocks=0)
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


class MembershipContainmentTests(unittest.TestCase):
    """F12 (Seq 139): a CreateEvent outside every sampled block was silently a cohort member.

    Measured before the fix: 24 clean strata, one member inside a block and one at a slot outside
    all of them — `CENSUS VERDICT: COMPLETE`, exit 0, `CreateEvents` reported as 2. Membership is
    the cohort definition, and every downstream figure is computed over `create_event`.
    """

    def build(self, extra_slot=None):
        path = pathlib.Path(tempfile.mkdtemp()) / "members.sqlite"
        connection = B8B.open_database(str(path))
        for hour in range(24):
            start = 1000 + hour * 1000
            connection.execute("INSERT INTO sampled_block VALUES (?,?,?,?,0,240)",
                               (hour, (27 * hour) % 59, start, start + 2))
            for slot in (start, start + 1):
                connection.execute("INSERT INTO slot_scan(slot,status,error,scanned_at_unix) "
                                   "VALUES (?,'retrieved',NULL,0)", (slot,))
            self.member(connection, start, hour)
        if extra_slot is not None:
            self.member(connection, extra_slot, 999)
        connection.commit()
        connection.close()
        return path

    def member(self, connection, slot, tag):
        connection.execute(
            "INSERT INTO create_event(slot,transaction_index,outer_instruction_index,"
            "inner_instruction_index,signature,mint,bonding_curve,creator,user,is_mayhem_mode,"
            "is_cashback_enabled,quote_mint,fields_json,event_payload_base64) "
            "VALUES (?,0,0,0,?,?,?,?,?,0,0,?,'{}','')",
            (slot, f"SIG{tag}", f"MINT{tag}", f"CURVE{tag}", f"C{tag}", f"C{tag}",
             CENSUS.SOL_SENTINEL))

    def run_census(self, path):
        import json
        import subprocess
        import sys
        out = path.with_suffix(".json")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "b8b_census.py"),
             "--database", str(path), "--json", str(out)],
            capture_output=True, text=True, cwd=str(ROOT))
        return result, json.loads(out.read_text())

    def test_a_cohort_wholly_inside_its_blocks_passes(self):
        result, report = self.run_census(self.build())
        self.assertEqual(report["cohort"]["members_outside_blocks"], 0)
        self.assertEqual(report["verdict"], "COMPLETE", report["failures"])
        self.assertEqual(result.returncode, 0)

    def test_a_member_outside_every_block_fails_end_to_end(self):
        """Call-site test as well as a behaviour test: the unit gate above passes even if `main()`
        never computes the figure, which is the fifth-time-lucky lesson from Seq 137."""
        result, report = self.run_census(self.build(extra_slot=999_999))
        self.assertEqual(report["cohort"]["members_outside_blocks"], 1)
        self.assertIn(999_999, report["cohort"]["slots_outside_blocks"])
        self.assertEqual(report["verdict"], "FAIL")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any("outside every sampled block" in f for f in report["failures"]),
                        report["failures"])

    def test_a_member_one_slot_past_a_block_end_is_outside(self):
        """`end_slot_exclusive` is exclusive; an off-by-one here would admit a non-member."""
        _, report = self.run_census(self.build(extra_slot=1002))   # block 0 is [1000, 1002)
        self.assertEqual(report["cohort"]["members_outside_blocks"], 1)
        self.assertEqual(report["verdict"], "FAIL")

    def test_a_member_on_the_last_slot_of_a_block_is_inside(self):
        """The other side of the same boundary — rejecting this would drop a real member."""
        _, report = self.run_census(self.build(extra_slot=1001))   # last slot of block 0
        self.assertEqual(report["cohort"]["members_outside_blocks"], 0)
        self.assertEqual(report["verdict"], "COMPLETE", report["failures"])



class ScheduleSlotBoundsTests(unittest.TestCase):
    """F10 (Seq 136): the mirror of F9, and the more dangerous half.

    F9 ties the schedule's TIMES to the declared window. Nothing tied its SLOTS — and the slots are
    what actually get fetched. A schedule with perfect times whose bounds sit five million slots
    away satisfied every check, would have fetched an entirely different span, and reported
    COMPLETE. The `% of the window` line does not help: it divides sampled-slot *count* by window
    width, so it still prints ~6.67% however far the slots have moved.
    """

    # `schedule_blocks` lays blocks out from slot 1000 upward, so this window contains them all.
    WINDOW_START, WINDOW_END = 1_000, 1_000_000

    def bounds(self, blocks):
        # Shape follows assert_schedule_slots_in_window(blocks, window_start, window_end, origin).
        # Every argument is required (Seq 138) - the anchor check is a separate function now, so
        # there is no optional parameter left to degrade into a silent no-op.
        return (blocks, self.WINDOW_START, self.WINDOW_END, "stored")

    def test_every_argument_is_required_so_a_dropped_one_cannot_no_op(self):
        """Seq 137 measured that dropping the optional bounds from the combined call left all 75
        tests green: the check degraded to a silent no-op rather than disappearing. Seq 137's own
        conclusion was that such an argument should be required unless there is a reason it cannot
        be. There is none here, so a missing argument must be a TypeError."""
        with self.assertRaises(TypeError):
            B8B.assert_schedule_slots_in_window(schedule_blocks(), self.WINDOW_START)
        with self.assertRaises(TypeError):
            B8B.assert_schedule_anchor(schedule_blocks())

    def test_an_in_window_schedule_passes(self):
        B8B.assert_schedule_slots_in_window(*self.bounds(schedule_blocks()))

    def test_slots_shifted_past_the_window_end_are_refused(self):
        blocks = [dict(b, start_slot=b["start_slot"] + 5_000_000,
                       end_slot_exclusive=b["end_slot_exclusive"] + 5_000_000)
                  for b in schedule_blocks()]
        with self.assertRaises(SystemExit) as ctx:
            B8B.assert_schedule_slots_in_window(*self.bounds(blocks))
        self.assertIn("outside the declared window", str(ctx.exception))

    def test_slots_shifted_before_the_window_start_are_refused(self):
        blocks = [dict(b, start_slot=b["start_slot"] - 5_000,
                       end_slot_exclusive=b["end_slot_exclusive"] - 5_000)
                  for b in schedule_blocks()]
        with self.assertRaises(SystemExit):
            B8B.assert_schedule_slots_in_window(*self.bounds(blocks))

    def test_a_single_block_straying_out_is_refused(self):
        """A whole-schedule shift is the obvious case; one drifted stratum is the quiet one."""
        blocks = schedule_blocks()
        blocks[9]["end_slot_exclusive"] = self.WINDOW_END + 2
        with self.assertRaises(SystemExit):
            B8B.assert_schedule_slots_in_window(*self.bounds(blocks))

    def test_a_block_ending_exactly_at_the_inclusive_window_end_is_allowed(self):
        """`window_end` is inclusive and `end_slot_exclusive` is not, so the bound is end+1.
        An off-by-one here would reject a legitimate schedule that reaches the final slot."""
        blocks = schedule_blocks()
        blocks[0]["end_slot_exclusive"] = self.WINDOW_END + 1
        B8B.assert_schedule_slots_in_window(*self.bounds(blocks))
        blocks[0]["end_slot_exclusive"] = self.WINDOW_END + 2
        with self.assertRaises(SystemExit):
            B8B.assert_schedule_slots_in_window(*self.bounds(blocks))

    def test_the_shifted_slots_really_do_pass_every_other_check(self):
        """Documents why this needs its own check: nothing else notices."""
        blocks = [dict(b, start_slot=b["start_slot"] + 5_000_000,
                       end_slot_exclusive=b["end_slot_exclusive"] + 5_000_000)
                  for b in schedule_blocks()]
        B8B.assert_complete_schedule(blocks, "internally coherent")      # passes
        B8B.assert_schedule_anchor(blocks, ANCHOR, "anchor only")  # F9 passes: times fine
        overlaps = [(a, b) for a, b in zip(blocks, blocks[1:])
                    if a["end_slot_exclusive"] > b["start_slot"]]
        self.assertEqual(overlaps, [], "the overlap check still passes")
        sampled = [s for b in blocks for s in range(b["start_slot"], b["end_slot_exclusive"])]
        self.assertEqual(len(sampled), len(set(sampled)), "the dedup check still passes")

    def test_bounds_are_optional_so_the_f9_only_call_still_works(self):
        """Callers passing no window still get the anchor check rather than a TypeError."""
        B8B.assert_schedule_anchor(schedule_blocks(), ANCHOR, "anchor only")

    def test_main_passes_the_window_bounds_through(self):
        """Call-site test, and it is load-bearing rather than ceremonial.

        The bounds are optional, so dropping them at the call site makes F10 **silently no-op** -
        every assertion above still passes. Verified by mutation: removing
        `args.window_start, args.window_end` from `main()` left all 75 tests green. That is the
        fifth call-site vacuity in this project (Seq 100, 109, 131, 135, and this one), and the
        first where the check degrades to a no-op instead of vanishing.

        Runs the real script with `--resolve-only` against a stored out-of-window schedule. No RPC:
        the stored path never resolves, and `--resolve-only` returns before any fetch.
        """
        import hashlib
        import json
        import os
        import subprocess
        import sys

        window_start, window_end, window_time = 1_000, 1_000_000, ANCHOR
        path = pathlib.Path(tempfile.mkdtemp()) / "outside.sqlite"
        connection = B8B.open_database(str(path))
        idl_sha = hashlib.sha256(
            (ROOT / "research" / "pump_idl_9c82f61.json").read_bytes()).hexdigest()
        meta = B8B.freeze_metadata(window_start, window_end, window_time,
                                   idl_sha, "public-mainnet")
        connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", meta.items())
        for block in schedule_blocks():                       # shifted clear of the window
            connection.execute(
                "INSERT INTO sampled_block VALUES (?,?,?,?,?,?)",
                (block["hour"], block["offset_minutes"], block["start_slot"] + 5_000_000,
                 block["end_slot_exclusive"] + 5_000_000, block["start_time"], block["end_time"]))
        connection.commit()
        connection.close()

        environment = dict(os.environ)
        environment.pop("SOLANA_RPC_URL", None)               # so endpoint_ref is public-mainnet
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "b8b_cohort_scanner.py"),
             "--database", str(path), "--window-start", str(window_start),
             "--window-end", str(window_end), "--window-start-time", str(window_time),
             "--resolve-only"],
            capture_output=True, text=True, cwd=str(ROOT), env=environment)
        self.assertNotEqual(result.returncode, 0,
                            f"main() accepted an out-of-window schedule.\n{result.stdout[-1500:]}")
        self.assertIn("outside the declared window", result.stdout + result.stderr)

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
        return schedule_blocks(count)

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
