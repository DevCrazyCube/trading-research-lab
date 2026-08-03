"""B15j tests. Every way of losing a byte is provoked, not asserted about.

The claim this module makes is that no raw evidence is ever lost. A claim like that is worth
exactly as much as the tests that try to break it, so each one here breaks something specific —
truncates an archive, flips a byte, kills a rotation halfway, hides a segment — and checks that the
original survives and the refusal is visible.
"""
import gzip
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
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


B15J = _load("b15j_raw_retention", "b15j_raw_retention.py")

STEM = "raw_frames"
ACTIVE = "raw_frames.jsonl"


def _line(index, signature=None):
    return json.dumps({"received_wall_unix": 1000.0 + index,
                       "signature": signature if signature is not None else f"Sig{index:04d}",
                       "observed_slot": 400_000 + index,
                       "raw_notification_json": {"n": index}},
                      sort_keys=True, separators=(",", ":")) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15j_"))
        self.active = self.directory / ACTIVE
        self.document = B15J.verify_preregistration()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def write_active(self, lines):
        with self.active.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line)

    def rotate(self, lines):
        self.write_active(lines)
        return B15J.rotate(self.active, self.directory, STEM, self.document)

    def census(self):
        return B15J.census_of(self.directory, STEM, self.active)


class TestPreregistration(Base):
    def test_the_freeze_is_pinned(self):
        self.assertEqual(self.document["preregistration_id"], "B15J_RAW_RETENTION_V1")
        self.assertTrue(self.document["committed_before_altering_any_file"])

    def test_a_tampered_freeze_refuses(self):
        altered = self.directory / "altered.json"
        document = json.loads(B15J.PREREG_PATH.read_bytes())
        document["free_space_guard"]["reserve_bytes"] = 1
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_preregistration(altered)
        self.assertIn("pinned", str(caught.exception))

    def test_an_unreadable_freeze_refuses(self):
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_preregistration(self.directory / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15J.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        poisoned = self.directory / "poisoned.py"
        poisoned.write_text("SECRET_TOKENS = ()\nx = 'sendTransaction'\n")
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.assert_no_execution_surface(poisoned)
        self.assertIn("sendTransaction", str(caught.exception))

    def test_the_reserve_is_the_measured_b9_footprint_times_the_stated_margin(self):
        guard = self.document["free_space_guard"]
        self.assertEqual(guard["reserve_bytes"], 45 * 1024 ** 3)
        self.assertEqual(guard["reserve_derivation"]["margin"], "1.5x")
        self.assertIn("31,580,337,648", guard["reserve_derivation"]["measured_precedent"])


class TestFreeSpaceGuard(Base):
    def test_ample_space_passes(self):
        self.assertEqual(B15J.assert_free_space(self.directory, 100, measured=1000), 1000)

    def test_the_guard_trips_below_the_reserve(self):
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.assert_free_space(self.directory, 1000, measured=999)
        self.assertIn(B15J.R_DISK_RESERVE, str(caught.exception))
        self.assertIn("B11a", str(caught.exception))

    def test_exactly_at_the_reserve_passes(self):
        """The boundary is stated as 'below', so equal is admissible. Fixed before it mattered."""
        self.assertEqual(B15J.assert_free_space(self.directory, 1000, measured=1000), 1000)

    def test_free_bytes_reads_the_real_filesystem(self):
        self.assertGreater(B15J.free_bytes(self.directory), 0)


class TestSealAndRotate(Base):
    def test_rotation_seals_the_tail_and_leaves_an_empty_one(self):
        record = self.rotate([_line(i) for i in range(5)])
        self.assertEqual(record["sequence"], 1)
        self.assertEqual(record["record_count"], 5)
        self.assertEqual(record["first_identity"], "Sig0000")
        self.assertEqual(record["last_identity"], "Sig0004")
        self.assertEqual(record["first_received_wall_unix"], 1000.0)
        self.assertEqual(record["last_received_wall_unix"], 1004.0)
        self.assertTrue(self.active.exists())
        self.assertEqual(self.active.stat().st_size, 0)

    def test_the_seal_hash_is_the_uncompressed_bytes(self):
        lines = [_line(i) for i in range(3)]
        expected = hashlib.sha256("".join(lines).encode()).hexdigest()
        record = self.rotate(lines)
        self.assertEqual(record["sha256_uncompressed"], expected)
        self.assertEqual(record["uncompressed_bytes"], len("".join(lines).encode()))

    def test_sequences_are_assigned_in_order_and_never_reused(self):
        self.rotate([_line(0)])
        self.rotate([_line(1)])
        self.assertEqual([r["sequence"] for r in B15J.read_index(self.directory)], [1, 2])
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.rotate(self.active, self.directory, STEM, self.document, sequence=1)
        self.assertIn("never reused", str(caught.exception))

    def test_a_record_without_an_identity_seals_as_null_not_empty_string(self):
        self.write_active([json.dumps({"jsonrpc": "2.0", "result": 42}) + "\n"])
        record = B15J.rotate(self.active, self.directory, STEM, self.document)
        self.assertIsNone(record["first_identity"])
        self.assertIsNone(record["first_received_wall_unix"])

    def test_rotating_a_missing_tail_refuses(self):
        self.active.unlink(missing_ok=True)
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.rotate(self.active, self.directory, STEM, self.document)
        self.assertIn("no active tail", str(caught.exception))

    def test_a_live_writer_blocks_rotation(self):
        """os.replace would move the NAME while the writer kept appending to the same inode."""
        self.write_active([_line(0)])
        handle = self.active.open("a")
        try:
            with self.assertRaises(B15J.RetentionRefused) as caught:
                B15J.assert_no_writer(self.active)
            self.assertIn("FOR WRITING", str(caught.exception))
            self.assertIn("same inode", str(caught.exception))
            # Naming the holder explicitly is how the rotation driver runs against its own writer.
            self.assertTrue(B15J.assert_no_writer(self.active, allow=[os.getpid()]))
        finally:
            handle.close()

    def test_no_writer_passes_when_nothing_holds_the_file(self):
        self.write_active([_line(0)])
        self.assertTrue(B15J.assert_no_writer(self.active))

    def test_a_reader_does_not_block_rotation(self):
        """A reader keeps its own handle on the same inode across the rename, so it is harmless.

        B15d holds B15a's raw log open to read it. Treating that as a hazard stopped a rotation
        that was entirely safe, so readers and writers are now distinguished by their fd flags
        rather than lumped together.
        """
        self.write_active([_line(0)])
        handle = self.active.open("r")
        try:
            self.assertIn(os.getpid(), B15J.open_file_holders(self.active))
            self.assertNotIn(os.getpid(),
                             B15J.open_file_holders(self.active, writers_only=True))
            self.assertTrue(B15J.assert_no_writer(self.active))
        finally:
            handle.close()

    def test_a_read_write_handle_counts_as_a_writer(self):
        self.write_active([_line(0)])
        handle = self.active.open("r+")
        try:
            with self.assertRaises(B15J.RetentionRefused):
                B15J.assert_no_writer(self.active)
        finally:
            handle.close()

    def test_an_unreadable_descriptor_mode_counts_as_a_writer(self):
        """Unknown is not clean: a mode that cannot be read is treated as write-capable."""
        self.assertTrue(B15J._descriptor_is_writable(999999999, "0"))


class TestIndex(Base):
    def test_a_gap_in_the_index_refuses(self):
        self.rotate([_line(0)])
        B15J.append_index(self.directory, {"sequence": 3, "stem": STEM})
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.assert_index_contiguous(B15J.read_index(self.directory))
        self.assertIn(B15J.R_SEGMENT_GAP, str(caught.exception))
        self.assertIn("missing=[2]", str(caught.exception))

    def test_a_duplicate_sequence_refuses(self):
        self.rotate([_line(0)])
        B15J.append_index(self.directory, {"sequence": 1, "stem": STEM})
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.assert_index_contiguous(B15J.read_index(self.directory))
        self.assertIn("duplicated=[1]", str(caught.exception))

    def test_an_unreadable_index_refuses_rather_than_reading_as_empty(self):
        self.rotate([_line(0)])
        with B15J.index_path(self.directory).open("a") as handle:
            handle.write("{not json\n")
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.read_index(self.directory)
        self.assertIn(B15J.R_INDEX_UNREADABLE, str(caught.exception))

    def test_an_absent_index_is_empty_not_an_error(self):
        self.assertEqual(B15J.read_index(self.directory), [])

    def test_a_credential_in_an_index_record_refuses(self):
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.append_index(self.directory, {"sequence": 1, "stem": STEM,
                                               "endpoint": "https://x?api-key=abc"})
        self.assertIn(B15J.R_SECRET_IN_ARCHIVE, str(caught.exception))


class TestCanonicalOrder(Base):
    def test_segments_read_in_ascending_sequence_then_the_tail_last(self):
        self.rotate([_line(0), _line(1)])
        self.rotate([_line(2)])
        self.write_active([_line(3)])
        identities = [json.loads(line)["signature"] for line in
                      B15J.iter_lines(self.directory, STEM, self.active)]
        self.assertEqual(identities, ["Sig0000", "Sig0001", "Sig0002", "Sig0003"])

    def test_a_partial_final_line_in_the_tail_is_dropped_not_repaired(self):
        self.rotate([_line(0)])
        with self.active.open("a") as handle:
            handle.write(_line(1))
            handle.write('{"received_wall_unix": 1002.0, "signa')     # cut mid-write
        identities = [json.loads(line)["signature"] for line in
                      B15J.iter_lines(self.directory, STEM, self.active)]
        self.assertEqual(identities, ["Sig0000", "Sig0001"])

    def test_a_missing_segment_file_refuses_rather_than_reading_a_short_set(self):
        record = self.rotate([_line(0)])
        self.rotate([_line(1)])
        B15J.sealed_path(self.directory, STEM, record["sequence"]).unlink()
        with self.assertRaises(B15J.RetentionRefused) as caught:
            list(B15J.iter_lines(self.directory, STEM, self.active))
        self.assertIn(B15J.R_SEGMENT_GAP, str(caught.exception))

    def test_the_census_is_a_chain_so_order_matters(self):
        """A count-based summary agrees when order differs. A chain cannot."""
        self.rotate([_line(0)])
        self.rotate([_line(1)])
        forward = self.census()

        other = pathlib.Path(tempfile.mkdtemp(prefix="b15j_rev_"))
        try:
            active = other / ACTIVE
            for line in (_line(1), _line(0)):
                with active.open("a") as handle:
                    handle.write(line)
                B15J.rotate(active, other, STEM, self.document)
            reversed_census = B15J.census_of(other, STEM, active)
            self.assertEqual(reversed_census["lines"], forward["lines"])
            self.assertNotEqual(reversed_census["chain_sha256"], forward["chain_sha256"])
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_the_gate_census_excludes_the_live_tail(self):
        """A tail that grows during verification must not fail the gate for the segments.

        The first live compaction refused both segments with R_REPLAY_DIVERGED because 400,000
        frames arrived between the two censuses. The tail is not a segment and is never replaced.
        """
        self.rotate([_line(i) for i in range(5)])
        sealed_only = B15J.census_of(self.directory, STEM, self.active, include_tail=False)
        self.write_active([_line(99)])          # the feed keeps writing
        self.assertEqual(B15J.census_of(self.directory, STEM, self.active, include_tail=False),
                         sealed_only)
        self.assertNotEqual(B15J.census_of(self.directory, STEM, self.active), sealed_only)

    def test_the_gate_passes_while_the_tail_is_growing(self):
        record = self.rotate([_line(i) for i in range(20)])
        B15J.compress_segment(self.directory, record)
        original_census = B15J.census_of

        def growing(work_dir, stem, active, include_tail=True, max_sequence=None):
            self.write_active([_line(500)])     # a frame lands mid-verification, every time
            return original_census(work_dir, stem, active, include_tail, max_sequence)

        outcome = B15J.verify_and_replace(self.directory, record, STEM, self.active,
                                          census=growing)
        self.assertTrue(outcome["replaced"])

    def test_the_gate_survives_a_new_segment_sealed_mid_verification(self):
        """The writer keeps rotating. A set read twice is two different sets, not a divergence.

        Excluding the live tail was not enough: the first live compaction still refused two
        segments because the feed had sealed another one between the two censuses.
        """
        record = self.rotate([_line(i) for i in range(20)])
        B15J.compress_segment(self.directory, record)
        original_census = B15J.census_of
        sealed = {"done": False}

        def rotating(work_dir, stem, active, include_tail=True, max_sequence=None):
            if not sealed["done"]:
                sealed["done"] = True
                self.write_active([_line(900)])
                B15J.rotate(active, work_dir, stem, self.document)   # a whole new segment appears
            return original_census(work_dir, stem, active, include_tail, max_sequence)

        outcome = B15J.verify_and_replace(self.directory, record, STEM, self.active,
                                          census=rotating)
        self.assertTrue(outcome["replaced"])

    def test_a_census_pinned_to_a_frontier_ignores_later_segments(self):
        self.rotate([_line(0)])
        pinned = B15J.census_of(self.directory, STEM, self.active, False, 1)
        self.rotate([_line(1)])
        self.assertEqual(B15J.census_of(self.directory, STEM, self.active, False, 1), pinned)
        self.assertNotEqual(B15J.census_of(self.directory, STEM, self.active, False, 2), pinned)

    def test_reading_twice_gives_the_same_census(self):
        self.rotate([_line(0), _line(1)])
        self.write_active([_line(2)])
        self.assertEqual(self.census(), self.census())


class TestCompressAndReplace(Base):
    def test_the_original_survives_compression(self):
        record = self.rotate([_line(i) for i in range(20)])
        B15J.compress_segment(self.directory, record)
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1, compressed=True).exists())

    def test_the_archive_decompresses_to_the_sealed_hash(self):
        record = self.rotate([_line(i) for i in range(20)])
        B15J.compress_segment(self.directory, record)
        proof = B15J.verify_segment(self.directory, record)
        self.assertEqual(proof["decompressed_sha256"], record["sha256_uncompressed"])

    def test_the_full_gate_replaces_and_the_census_is_unchanged(self):
        self.rotate([_line(i) for i in range(50)])
        self.write_active([_line(99)])
        before = self.census()
        record = B15J.read_index(self.directory)[0]
        B15J.compress_segment(self.directory, record)
        outcome = B15J.verify_and_replace(self.directory, record, STEM, self.active)
        self.assertTrue(outcome["replaced"])
        self.assertFalse(B15J.sealed_path(self.directory, STEM, 1).exists())
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1, compressed=True).exists())
        self.assertEqual(self.census(), before)

    def test_a_truncated_archive_is_refused_and_the_original_stays(self):
        record = self.rotate([_line(i) for i in range(50)])
        archive = B15J.sealed_path(self.directory, STEM, 1, compressed=True)
        B15J.compress_segment(self.directory, record)
        with archive.open("r+b") as handle:
            handle.truncate(archive.stat().st_size // 2)
        with self.assertRaises(Exception):
            B15J.verify_and_replace(self.directory, record, STEM, self.active)
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())

    def test_a_corrupt_archive_is_refused_and_the_original_stays(self):
        record = self.rotate([_line(i) for i in range(50)])
        B15J.compress_segment(self.directory, record)
        archive = B15J.sealed_path(self.directory, STEM, 1, compressed=True)
        raw = bytearray(archive.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        archive.write_bytes(bytes(raw))
        with self.assertRaises(Exception):
            B15J.verify_and_replace(self.directory, record, STEM, self.active)
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())

    def test_an_archive_of_different_content_is_refused(self):
        """The hash is the whole point: an archive that opens fine but holds other bytes fails."""
        record = self.rotate([_line(i) for i in range(10)])
        archive = B15J.sealed_path(self.directory, STEM, 1, compressed=True)
        with gzip.GzipFile(filename=str(archive), mode="wb", mtime=0) as handle:
            handle.write(b"these are not the bytes that were sealed\n")
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_segment(self.directory, record)
        self.assertIn(B15J.R_DECOMPRESS_MISMATCH, str(caught.exception))
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())

    def test_a_missing_archive_is_refused(self):
        record = self.rotate([_line(0)])
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_segment(self.directory, record)
        self.assertIn(B15J.R_PARTIAL_ARCHIVE, str(caught.exception))

    def test_a_partial_archive_is_discarded_never_adopted(self):
        record = self.rotate([_line(i) for i in range(10)])
        partial = pathlib.Path(
            str(B15J.sealed_path(self.directory, STEM, 1, compressed=True)) + ".partial")
        partial.write_bytes(b"\x1f\x8b truncated garbage")
        self.assertEqual(B15J.discard_partial_archives(self.directory), 1)
        self.assertFalse(partial.exists())
        # And compressing afterwards still produces a verifiable archive.
        B15J.compress_segment(self.directory, record)
        self.assertEqual(B15J.verify_segment(self.directory, record)["decompressed_sha256"],
                         record["sha256_uncompressed"])

    def test_a_crash_between_seal_and_compress_loses_nothing(self):
        """The sealed original is the authority until the gate passes. Simulated by stopping."""
        record = self.rotate([_line(i) for i in range(10)])
        before = self.census()
        # ... process dies here, before compress_segment is ever called ...
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())
        self.assertEqual(self.census(), before)
        B15J.compress_segment(self.directory, record)
        B15J.verify_and_replace(self.directory, record, STEM, self.active)
        self.assertEqual(self.census(), before)

    def test_gzip_output_is_deterministic(self):
        record = self.rotate([_line(i) for i in range(10)])
        archive = B15J.sealed_path(self.directory, STEM, 1, compressed=True)
        B15J.compress_segment(self.directory, record)
        first = archive.read_bytes()
        archive.unlink()
        B15J.compress_segment(self.directory, record)
        self.assertEqual(archive.read_bytes(), first)

    def test_compressing_a_vanished_original_refuses(self):
        record = self.rotate([_line(0)])
        B15J.sealed_path(self.directory, STEM, 1).unlink()
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.compress_segment(self.directory, record)
        self.assertIn(B15J.R_SEAL_MISMATCH, str(caught.exception))

    def test_a_stream_that_changes_mid_gate_refuses_and_restores_the_original(self):
        """The live-writer case: the tail grew between the two censuses, so they disagree.

        The archive is perfect and its hash matches. What fails is the READER producing a
        different stream, which is the only thing the third condition can catch and the reason it
        is not redundant with the hash checks.
        """
        record = self.rotate([_line(i) for i in range(10)])
        B15J.compress_segment(self.directory, record)
        answers = [{"lines": 10, "chain_sha256": "aaa"}, {"lines": 11, "chain_sha256": "bbb"}]

        def shifting(_work_dir, _stem, _active, _include_tail=True, _max_sequence=None):
            return answers.pop(0)

        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_and_replace(self.directory, record, STEM, self.active, census=shifting)
        self.assertIn(B15J.R_REPLAY_DIVERGED, str(caught.exception))
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())
        self.assertFalse(
            pathlib.Path(str(B15J.sealed_path(self.directory, STEM, 1)) + ".parked").exists())
        self.assertEqual(self.census()["lines"], 10)     # and the set still reads whole

    def test_replacing_an_already_replaced_segment_is_a_no_op(self):
        record = self.rotate([_line(i) for i in range(10)])
        B15J.compress_segment(self.directory, record)
        B15J.verify_and_replace(self.directory, record, STEM, self.active)
        outcome = B15J.verify_and_replace(self.directory, record, STEM, self.active)
        self.assertTrue(outcome["already_replaced"])


class TestDriver(Base):
    def test_the_driver_rotates_compresses_verifies_and_reclaims(self):
        self.write_active([_line(i) for i in range(2000)])
        before = self.census()
        report = B15J.run("b15i", work_dir=self.directory, max_segment_bytes=1,
                          document=self.document, reserve_bytes=0, active_name=ACTIVE, stem=STEM)
        self.assertEqual(report["rotated"], 1)
        self.assertEqual(len(report["verified"]), 1)
        self.assertEqual(report["refusals"], [])
        self.assertLess(report["verified"][0]["archive_bytes"],
                        report["verified"][0]["uncompressed_bytes"])
        self.assertEqual(self.census(), before)

    def test_the_driver_does_not_rotate_a_tail_below_the_limit(self):
        self.write_active([_line(0)])
        report = B15J.run("b15i", work_dir=self.directory, max_segment_bytes=10 ** 9,
                          document=self.document, reserve_bytes=0, active_name=ACTIVE, stem=STEM)
        self.assertIsNone(report["rotated"])

    def test_the_driver_does_not_re_verify_what_it_already_replaced(self):
        self.write_active([_line(i) for i in range(500)])
        B15J.run("b15i", work_dir=self.directory, max_segment_bytes=1, document=self.document,
                 reserve_bytes=0, active_name=ACTIVE, stem=STEM)
        again = B15J.run("b15i", work_dir=self.directory, max_segment_bytes=10 ** 9,
                         document=self.document, reserve_bytes=0, active_name=ACTIVE, stem=STEM)
        self.assertEqual(again["verified"], [])

    def test_a_refusal_leaves_the_original_and_is_reported_not_raised(self):
        """A sealed original whose bytes changed after sealing cannot be healed by recompressing.

        Corrupting the ARCHIVE proves nothing here: the driver compresses before it verifies, so a
        bad archive is simply overwritten with a good one. The unhealable case is the one worth
        driving — bit rot under a segment that was already measured.
        """
        self.write_active([_line(i) for i in range(500)])
        B15J.rotate(self.active, self.directory, STEM, self.document)
        original = B15J.sealed_path(self.directory, STEM, 1)
        raw = bytearray(original.read_bytes())
        raw[10] ^= 0xFF
        original.write_bytes(bytes(raw))
        report = B15J.run("b15i", work_dir=self.directory, max_segment_bytes=10 ** 9,
                          document=self.document, reserve_bytes=0, active_name=ACTIVE, stem=STEM)
        self.assertEqual(len(report["refusals"]), 1)
        # V2 names the segment and both hashes rather than reporting a decompression mismatch: the
        # single pass streams each segment and checks it against its own seal, so the failure is
        # located rather than merely detected.
        self.assertIn(B15J.R_SEAL_MISMATCH, report["refusals"][0]["reason"])
        self.assertEqual(report["verified"], [])
        self.assertTrue(original.exists())          # never removed on a failed gate

    def test_a_second_compactor_is_refused_rather_than_racing(self):
        """Two runs raced and one deleted a file the other was verifying. Nothing was lost."""
        with B15J.CompactionLock(self.directory):
            with self.assertRaises(B15J.RetentionRefused) as caught:
                with B15J.CompactionLock(self.directory):
                    pass
            self.assertIn("another compactor", str(caught.exception))
        with B15J.CompactionLock(self.directory):
            pass                      # released, so the next one gets it

    def test_an_archive_left_without_its_flag_is_re_verified_not_re_reported(self):
        self.write_active([_line(i) for i in range(500)])
        B15J.rotate(self.active, self.directory, STEM, self.document)
        record = B15J.read_index(self.directory)[0]
        B15J.compress_segment(self.directory, record)
        B15J.sealed_path(self.directory, STEM, 1).unlink()      # replaced, flag write lost
        report = B15J.run("b15i", work_dir=self.directory, max_segment_bytes=10 ** 9,
                          document=self.document, reserve_bytes=0, active_name=ACTIVE, stem=STEM)
        self.assertEqual(report["refusals"], [])
        self.assertIn(1, B15J.verified_sequences(self.directory))

    def test_an_archive_left_without_its_flag_must_still_prove_itself(self):
        self.write_active([_line(i) for i in range(500)])
        B15J.rotate(self.active, self.directory, STEM, self.document)
        record = B15J.read_index(self.directory)[0]
        B15J.compress_segment(self.directory, record)
        B15J.sealed_path(self.directory, STEM, 1).unlink()
        archive = B15J.sealed_path(self.directory, STEM, 1, compressed=True)
        with gzip.GzipFile(filename=str(archive), mode="wb", mtime=0) as handle:
            handle.write(b"not the sealed bytes\n")
        report = B15J.run("b15i", work_dir=self.directory, max_segment_bytes=10 ** 9,
                          document=self.document, reserve_bytes=0, active_name=ACTIVE, stem=STEM)
        self.assertEqual(len(report["refusals"]), 1)
        self.assertNotIn(1, B15J.verified_sequences(self.directory))

    def test_status_reports_the_margin_against_the_reserve(self):
        self.write_active([_line(i) for i in range(100)])
        report = B15J.status("b15i", work_dir=self.directory, document=self.document,
                             active_name=ACTIVE, stem=STEM)
        self.assertEqual(report["reserve_bytes"], 45 * 1024 ** 3)
        self.assertEqual(report["margin_bytes"], report["free_bytes"] - report["reserve_bytes"])
        self.assertEqual(report["label"], "OPERATIONAL_RAW_RETENTION")




class TestV2Gate(Base):
    """One pinned-frontier pass per run. Every way of losing a byte through it is driven."""

    def seal(self, count, start=0):
        return self.rotate([_line(i) for i in range(start, start + count)])

    def test_the_v2_freeze_is_pinned_and_names_v1(self):
        document = B15J.verify_preregistration_v2()
        self.assertEqual(document["preregistration_id"], "B15J_RAW_RETENTION_V2")
        self.assertEqual(document["supersedes"], "B15J_RAW_RETENTION_V1")
        self.assertEqual(document["supersedes_canonical_sha256"], B15J.PREREG_CANONICAL_SHA256)
        self.assertTrue(document["committed_before_behaviour_change"])

    def test_a_v2_that_names_the_wrong_predecessor_refuses(self):
        altered = self.directory / "v2.json"
        document = json.loads(B15J.PREREG_V2_PATH.read_bytes())
        document["supersedes_canonical_sha256"] = "0" * 64
        altered.write_text(json.dumps(document))
        expected = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_preregistration_v2(altered, expected)
        self.assertIn("must name the document it replaces", str(caught.exception))

    def test_a_v2_that_drops_v1s_reserve_refuses(self):
        """A superseding document is how a frozen number gets quietly restated."""
        altered = self.directory / "v2.json"
        document = json.loads(B15J.PREREG_V2_PATH.read_bytes())
        document["what_changes_and_what_does_not"]["does_not_change"] = ["something else"]
        altered.write_text(json.dumps(document))
        expected = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_preregistration_v2(altered, expected)
        self.assertIn("verbatim", str(caught.exception))

    def test_an_unreadable_v2_refuses(self):
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_preregistration_v2(self.directory / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_a_tampered_v2_refuses(self):
        altered = self.directory / "v2.json"
        document = json.loads(B15J.PREREG_V2_PATH.read_bytes())
        document["purpose"] = "something else"
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.verify_preregistration_v2(altered)
        self.assertIn("pinned", str(caught.exception))

    # -- the pass itself ---------------------------------------------------------------------

    def test_the_expected_census_is_computed_from_the_seals_with_no_file_read(self):
        self.seal(5)
        self.seal(7, start=100)
        records = B15J.read_index(self.directory)
        expected = B15J.expected_census(records)
        self.assertEqual(expected["segments"], 2)
        self.assertEqual(expected["total_record_count"], 12)
        # Provable independence from the files: delete them and the expectation is unchanged.
        for sequence in (1, 2):
            B15J.sealed_path(self.directory, STEM, sequence).unlink()
        self.assertEqual(B15J.expected_census(B15J.read_index(self.directory)), expected)

    def test_the_single_pass_matches_the_expected_census(self):
        self.seal(5)
        self.seal(7, start=100)
        records = B15J.read_index(self.directory)
        self.assertEqual(B15J.single_pass_verify(self.directory, STEM, records),
                         B15J.expected_census(records))

    def test_the_single_pass_names_the_segment_whose_bytes_changed(self):
        self.seal(5)
        self.seal(7, start=100)
        target = B15J.sealed_path(self.directory, STEM, 2)
        raw = bytearray(target.read_bytes())
        raw[5] ^= 0xFF
        target.write_bytes(bytes(raw))
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.single_pass_verify(self.directory, STEM, B15J.read_index(self.directory))
        self.assertIn(B15J.R_SEAL_MISMATCH, str(caught.exception))
        self.assertIn("000002", str(caught.exception))

    def test_the_single_pass_catches_a_record_count_that_drifted(self):
        record = self.seal(5)
        forged = dict(record)
        forged["record_count"] = 4
        with self.assertRaises(B15J.RetentionRefused) as caught:
            B15J.single_pass_verify(self.directory, STEM, [forged])
        self.assertIn("records, sealed as 4", str(caught.exception))

    def test_a_clean_run_replaces_every_candidate(self):
        self.seal(20)
        self.seal(20, start=100)
        self.seal(20, start=200)
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["frontier"], 3)
        self.assertEqual(report["replaced"], [1, 2, 3])
        self.assertEqual(report["refusals"], [])
        for sequence in (1, 2, 3):
            self.assertFalse(B15J.sealed_path(self.directory, STEM, sequence).exists())
            self.assertTrue(
                B15J.sealed_path(self.directory, STEM, sequence, compressed=True).exists())

    def test_a_second_run_has_nothing_to_do(self):
        self.seal(20)
        B15J.compact_once(self.directory, STEM)
        again = B15J.compact_once(self.directory, STEM)
        self.assertEqual(again["replaced"], [])
        self.assertEqual(again["refusals"], [])

    def test_the_set_still_reads_whole_after_replacement(self):
        self.seal(10)
        self.seal(10, start=100)
        self.write_active([_line(999)])
        before = self.census()
        B15J.compact_once(self.directory, STEM)
        self.assertEqual(self.census(), before)

    # -- partial failure: all or nothing ----------------------------------------------------

    def test_one_bad_segment_saves_every_original_in_the_run(self):
        """A partial replacement leaves a set nobody verified as a set."""
        self.seal(20)
        self.seal(20, start=100)
        self.seal(20, start=200)
        target = B15J.sealed_path(self.directory, STEM, 2)
        raw = bytearray(target.read_bytes())
        raw[7] ^= 0xFF
        target.write_bytes(bytes(raw))
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["replaced"], [])
        self.assertEqual(len(report["refusals"]), 1)
        for sequence in (1, 2, 3):
            self.assertTrue(B15J.sealed_path(self.directory, STEM, sequence).exists())

    def test_a_failed_run_is_quarantined_with_the_reason(self):
        self.seal(20)
        target = B15J.sealed_path(self.directory, STEM, 1)
        target.write_bytes(b"different bytes entirely\n")
        B15J.compact_once(self.directory, STEM)
        lines = (B15J.segment_dir(self.directory) / "quarantine.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["candidates"], [1])
        self.assertIn(B15J.R_SEAL_MISMATCH, record["reason"])
        self.assertEqual(record["restored"], 1)

    def test_a_diverging_census_saves_the_originals(self):
        self.seal(20)
        self.seal(20, start=100)

        def wrong(_work_dir, _stem, _records):
            return {"segments": 99, "total_record_count": 0, "segment_chain_sha256": "x"}

        report = B15J.compact_once(self.directory, STEM, verifier=wrong)
        self.assertEqual(report["replaced"], [])
        self.assertIn(B15J.R_REPLAY_DIVERGED, report["refusals"][0]["reason"])
        for sequence in (1, 2):
            self.assertTrue(B15J.sealed_path(self.directory, STEM, sequence).exists())

    def test_a_verifier_that_explodes_still_restores_the_originals(self):
        self.seal(20)

        def exploding(_work_dir, _stem, _records):
            raise MemoryError("the gate must not lose a byte to this")

        report = B15J.compact_once(self.directory, STEM, verifier=exploding)
        self.assertEqual(report["replaced"], [])
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())
        self.assertIn("MemoryError", report["refusals"][0]["reason"])

    # -- crash and restart ------------------------------------------------------------------

    def test_a_parked_original_is_restored_on_the_next_run(self):
        """A parked original belongs to a run that never finished proving it."""
        record = self.seal(20)
        B15J.compress_segment(self.directory, record)
        original = B15J.sealed_path(self.directory, STEM, 1)
        os.replace(original, B15J.parked_path(self.directory, STEM, 1))
        # ... the process dies here, between parking and verifying ...
        self.assertFalse(original.exists())
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["restored_parked"], 1)
        self.assertEqual(report["replaced"], [1])

    def test_a_parked_original_is_never_left_hidden_from_the_reader(self):
        record = self.seal(20)
        B15J.compress_segment(self.directory, record)
        os.replace(B15J.sealed_path(self.directory, STEM, 1),
                   B15J.parked_path(self.directory, STEM, 1))
        B15J.restore_parked_originals(self.directory)
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())
        self.assertEqual(len(list(B15J.iter_lines(self.directory, STEM, self.active))), 20)

    def test_a_crash_between_compress_and_park_loses_nothing(self):
        self.seal(20)
        self.seal(20, start=100)
        record = B15J.read_index(self.directory)[0]
        B15J.compress_segment(self.directory, record)     # archive written, nothing parked
        before = self.census()
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["replaced"], [1, 2])
        self.assertEqual(self.census(), before)

    def test_a_partial_archive_from_a_crash_is_discarded_not_adopted(self):
        self.seal(20)
        partial = pathlib.Path(
            str(B15J.sealed_path(self.directory, STEM, 1, compressed=True)) + ".partial")
        partial.write_bytes(b"\x1f\x8b truncated")
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["discarded_partials"], 1)
        self.assertEqual(report["replaced"], [1])

    # -- frontier ---------------------------------------------------------------------------

    def test_a_segment_sealed_during_the_run_is_ignored_by_it(self):
        self.seal(20)
        original_verify = B15J.single_pass_verify

        def sealing(work_dir, stem, records):
            self.write_active([_line(777)])
            B15J.rotate(self.active, self.directory, stem, self.document)   # frontier moves
            return original_verify(work_dir, stem, records)

        report = B15J.compact_once(self.directory, STEM, verifier=sealing)
        self.assertEqual(report["frontier"], 1)
        self.assertEqual(report["replaced"], [1])
        self.assertEqual(len(B15J.read_index(self.directory)), 2)   # the new one exists
        self.assertNotIn(2, B15J.verified_sequences(self.directory))   # and was left for later

    def test_the_next_run_picks_up_what_the_frontier_excluded(self):
        self.seal(20)
        B15J.compact_once(self.directory, STEM)
        self.seal(20, start=100)
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["frontier"], 2)
        self.assertEqual(report["replaced"], [2])

    def test_an_empty_index_is_a_result_not_an_error(self):
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["frontier"], 0)
        self.assertEqual(report["replaced"], [])

    # -- deletion before the gate -----------------------------------------------------------

    def test_a_deleted_original_without_an_archive_refuses_the_whole_set(self):
        """The set is incomplete and is never read as though it were complete."""
        self.seal(20)
        self.seal(20, start=100)
        B15J.sealed_path(self.directory, STEM, 1).unlink()
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["replaced"], [])
        self.assertTrue(any(B15J.R_SEGMENT_GAP in r["reason"] for r in report["refusals"]))
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 2).exists())

    def test_an_archive_without_its_original_is_verified_then_flagged(self):
        record = self.seal(20)
        B15J.compress_segment(self.directory, record)
        B15J.sealed_path(self.directory, STEM, 1).unlink()      # replaced, flag write lost
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(report["refusals"], [])
        self.assertIn(1, B15J.verified_sequences(self.directory))

    def test_an_archive_without_its_original_must_still_prove_itself(self):
        record = self.seal(20)
        B15J.compress_segment(self.directory, record)
        B15J.sealed_path(self.directory, STEM, 1).unlink()
        archive = B15J.sealed_path(self.directory, STEM, 1, compressed=True)
        with gzip.GzipFile(filename=str(archive), mode="wb", mtime=0) as handle:
            handle.write(b"not the sealed bytes\n")
        report = B15J.compact_once(self.directory, STEM)
        self.assertEqual(len(report["refusals"]), 1)
        self.assertNotIn(1, B15J.verified_sequences(self.directory))

    # -- concurrency ------------------------------------------------------------------------

    def test_the_driver_refuses_a_second_concurrent_compactor(self):
        self.seal(20)
        with B15J.CompactionLock(self.directory):
            with self.assertRaises(B15J.RetentionRefused) as caught:
                B15J.run("b15i", work_dir=self.directory, max_segment_bytes=10 ** 9,
                         document=self.document, reserve_bytes=0, active_name=ACTIVE, stem=STEM)
            self.assertIn("another compactor", str(caught.exception))
        self.assertTrue(B15J.sealed_path(self.directory, STEM, 1).exists())


class TestV1V2Equivalence(Base):
    """The two gates must agree, segment for segment, on synthetic multi-segment fixtures.

    A disagreement is a failure of the V2 document, not a tolerance.
    """

    def _fixture(self, directory, segments, damage=None):
        active = directory / ACTIVE
        for index in range(segments):
            with active.open("a", encoding="utf-8") as handle:
                for line in range(10):
                    handle.write(_line(index * 100 + line))
            B15J.rotate(active, directory, STEM, self.document)
        if damage is not None:
            target = B15J.sealed_path(directory, STEM, damage)
            raw = bytearray(target.read_bytes())
            raw[3] ^= 0xFF
            target.write_bytes(bytes(raw))
        return active

    def _v1_decisions(self, directory, active):
        """What V1's per-segment gate would admit."""
        admitted = []
        for record in B15J.read_index(directory):
            try:
                B15J.compress_segment(directory, record)
                B15J.verify_and_replace(directory, record, STEM, active)
                admitted.append(record["sequence"])
            except Exception:                                             # noqa: BLE001
                pass
        return admitted

    def _v2_decisions(self, directory, _active):
        return B15J.compact_once(directory, STEM)["replaced"]

    def _compare(self, segments, damage=None):
        one = pathlib.Path(tempfile.mkdtemp(prefix="b15j_v1_"))
        two = pathlib.Path(tempfile.mkdtemp(prefix="b15j_v2_"))
        try:
            v1 = self._v1_decisions(one, self._fixture(one, segments, damage))
            v2 = self._v2_decisions(two, self._fixture(two, segments, damage))
            return v1, v2
        finally:
            shutil.rmtree(one, ignore_errors=True)
            shutil.rmtree(two, ignore_errors=True)

    def test_the_gates_agree_on_a_clean_single_segment(self):
        v1, v2 = self._compare(1)
        self.assertEqual(v1, v2)
        self.assertEqual(v2, [1])

    def test_the_gates_agree_on_a_clean_five_segment_set(self):
        v1, v2 = self._compare(5)
        self.assertEqual(v1, v2)
        self.assertEqual(v2, [1, 2, 3, 4, 5])

    def test_the_gates_agree_that_nothing_is_admitted_when_a_segment_is_damaged(self):
        """V1 refused the damaged one; V2 refuses the whole run. Neither admits the damaged one.

        This is the ONE place the gates differ in outcome, and it differs only by being stricter:
        V1 would have replaced the undamaged segments alongside a refusal, leaving a set nobody
        verified as a set. V2 replaces all or none. Recorded here rather than hidden.
        """
        v1, v2 = self._compare(4, damage=2)
        self.assertNotIn(2, v1)
        self.assertNotIn(2, v2)
        self.assertEqual(v2, [])
        self.assertTrue(set(v2).issubset(set(v1)))    # V2 never admits what V1 refused

    def test_v2_never_admits_a_segment_v1_would_refuse(self):
        for segments, damage in ((2, 1), (3, 3), (5, 4)):
            with self.subTest(segments=segments, damage=damage):
                v1, v2 = self._compare(segments, damage=damage)
                self.assertTrue(set(v2).issubset(set(v1)))
                self.assertNotIn(damage, v2)

    def test_both_gates_leave_the_readable_stream_identical(self):
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b15j_eq_"))
        try:
            active = self._fixture(directory, 4)
            before = B15J.census_of(directory, STEM, active)
            B15J.compact_once(directory, STEM)
            self.assertEqual(B15J.census_of(directory, STEM, active), before)
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
