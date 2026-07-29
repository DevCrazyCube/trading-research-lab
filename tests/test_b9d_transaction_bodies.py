"""Offline tests for the B9d scaffold.

Every test here runs with no network and no dependency on the 840 MiB B9c artifact: the population
logic is exercised against small synthetic databases built to the same schema. The real artifact is
asserted at run time by `verify`, which is where a mismatch must stop a run — a unit test that
streams 1.35M rows would move that check into the suite and slow it into disuse.
"""
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9d", ROOT / "scripts" / "b9d_transaction_bodies.py")
B9D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9D)


def build_sources(directory, rows, outcomes):
    """Minimal B9c/B9a pair. `rows` are (curve, signature, err_json, slot, time_class)."""
    b9c = directory / "b9c.sqlite"
    b9a = directory / "b9a.sqlite"
    with sqlite3.connect(b9c) as con:
        con.execute("CREATE TABLE signature_observation (bonding_curve TEXT, signature TEXT, "
                    "slot INTEGER, block_time INTEGER, err_json TEXT, memo TEXT, "
                    "confirmation_status TEXT, page_index INTEGER, row_index INTEGER, "
                    "time_class TEXT)")
        con.executemany(
            "INSERT INTO signature_observation (bonding_curve, signature, err_json, slot, "
            "time_class) VALUES (?,?,?,?,?)", rows)
    with sqlite3.connect(b9a) as con:
        con.execute("CREATE TABLE outcome (bonding_curve TEXT, is_mayhem_mode INTEGER)")
        con.executemany("INSERT INTO outcome VALUES (?,?)", outcomes)
    return b9c, b9a


class PopulationTests(unittest.TestCase):
    """§3 and §1a: the fetch set, and the predicate that silently inverts it."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())

    def population(self, rows, outcomes):
        b9c, b9a = build_sources(self.dir, rows, outcomes)
        return B9D.frozen_population(str(b9c), str(b9a), assert_counts=False)

    def test_selects_only_successful_in_window_non_mayhem(self):
        rows = [
            ("curveA", "sigOK",      "null",                     100, "in_window"),
            ("curveA", "sigFailed",  '{"InstructionError":[]}',  101, "in_window"),
            ("curveA", "sigLate",    "null",                     102, "after_cutoff"),
            ("curveA", "sigEarly",   "null",                      99, "before_launch"),
            ("curveM", "sigMayhem",  "null",                     103, "in_window"),
        ]
        signatures, slots = self.population(rows, [("curveA", 0), ("curveM", 1)])
        self.assertEqual(signatures, {"sigOK"})
        self.assertEqual(slots, {100})

    def test_success_is_the_string_null_not_sql_null(self):
        """§1a. `err_json IS NULL` matched nothing and marked all 1,347,469 signatures failed.

        The wrong predicate is the one a reader reaches for by reflex and it leaves every other
        published figure intact, so it has to be pinned by a test rather than by a comment.
        """
        self.assertEqual(B9D.SUCCESS_PREDICATE, "err_json = 'null'")
        rows = [("curveA", "sigOK", "null", 100, "in_window"),
                ("curveA", "sigSqlNull", None, 101, "in_window")]
        signatures, _ = self.population(rows, [("curveA", 0)])
        self.assertEqual(signatures, {"sigOK"},
                         "a SQL-NULL err_json is not a success and must not be fetched")

    def test_a_signature_seen_on_two_curves_is_one_fetch(self):
        """Exact cross-curve deduplication is the one narrowing B9c authorised."""
        rows = [("curveA", "shared", "null", 100, "in_window"),
                ("curveB", "shared", "null", 100, "in_window")]
        signatures, slots = self.population(rows, [("curveA", 0), ("curveB", 0)])
        self.assertEqual(len(signatures), 1)
        self.assertEqual(slots, {100})

    def test_a_curve_missing_from_b9a_fails_visibly(self):
        rows = [("curveGhost", "sig", "null", 100, "in_window")]
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.population(rows, [("curveA", 0)])
        self.assertIn("bidirectionally", str(ctx.exception))

    def test_a_null_slot_stops_the_run(self):
        """§6 needs a slot per signature to find its transaction index; null is unknown, not gone."""
        rows = [("curveA", "sig", "null", None, "in_window")]
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.population(rows, [("curveA", 0)])
        self.assertIn("null slot", str(ctx.exception))


class PopulationAssertionTests(unittest.TestCase):
    """§3: a derived fetch set that is not the frozen one stops before any network call."""

    def test_frozen_constants_match_the_published_measurement(self):
        self.assertEqual(B9D.EXPECTED_SIGNATURES, 94_985)
        self.assertEqual(B9D.EXPECTED_SLOTS, 38_853)
        self.assertEqual(B9D.SLOT_MIN, 433_894_233)
        self.assertEqual(B9D.SLOT_MAX, 435_536_000)
        self.assertEqual(B9D.EXPECTED_SIGNATURES + B9D.EXPECTED_SLOTS, 133_838)

    def test_the_exact_frozen_population_passes(self):
        signatures = {f"s{i}" for i in range(B9D.EXPECTED_SIGNATURES)}
        slots = set(range(B9D.SLOT_MIN, B9D.SLOT_MIN + B9D.EXPECTED_SLOTS - 1)) | {B9D.SLOT_MAX}
        self.assertTrue(B9D.assert_population(signatures, slots))

    def test_a_short_population_stops(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_population({"a"}, {B9D.SLOT_MIN, B9D.SLOT_MAX})
        self.assertIn("94,985", str(ctx.exception))

    def test_a_wrong_slot_count_stops(self):
        signatures = {f"s{i}" for i in range(B9D.EXPECTED_SIGNATURES)}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_population(signatures, {B9D.SLOT_MIN, B9D.SLOT_MAX})
        self.assertIn("38,853", str(ctx.exception))


class SourceHashTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())

    def test_a_source_whose_hash_moved_is_refused(self):
        fake = self.dir / "b9c.sqlite"
        fake.write_bytes(b"not the artifact")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_sources(str(fake), str(fake))
        self.assertIn("refusing", str(ctx.exception))

    def test_sha256_file_matches_hashlib(self):
        blob = self.dir / "blob"
        blob.write_bytes(b"x" * (1 << 20) + b"tail")
        self.assertEqual(B9D.sha256_file(str(blob)),
                         hashlib.sha256(blob.read_bytes()).hexdigest())


class TransactionCoordinateTests(unittest.TestCase):
    """§6: the coordinate `getTransaction` does not supply.

    This is the defect Codex found in the original freeze (Seq 198): the ordering key required
    `transaction_index` while the frozen fetch method could not produce it.
    """

    def test_index_is_the_position_in_the_block_signature_list(self):
        block = ["a", "b", "c", "d"]
        self.assertEqual(B9D.transaction_coordinates(7, block, ["c", "a"]), {"c": 2, "a": 0})

    def test_a_duplicate_signature_in_one_block_fails_visibly(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.transaction_coordinates(7, ["a", "b", "a"], ["a"])
        self.assertIn("unique", str(ctx.exception))

    def test_a_signature_absent_from_its_block_fails_visibly(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.transaction_coordinates(7, ["a", "b"], ["a", "zzz"])
        self.assertIn("missing", str(ctx.exception))

    def test_slot_disagreement_between_block_and_transaction_fails(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.reconcile_slot("sig", 100, 101)
        self.assertIn("disagreeing", str(ctx.exception))
        self.assertTrue(B9D.reconcile_slot("sig", 100, 100))

    def test_an_incomplete_ordering_key_is_refused(self):
        self.assertEqual(B9D.canonical_key(1, 2, 3, -1), (1, 2, 3, -1))
        for missing in ((None, 2, 3, 4), (1, None, 3, 4), (1, 2, None, 4), (1, 2, 3, None)):
            with self.assertRaises(B9D.FreezeViolation):
                B9D.canonical_key(*missing)

    def test_outer_instructions_sort_before_their_own_inner_calls(self):
        keys = [B9D.canonical_key(5, 0, 1, -1), B9D.canonical_key(5, 0, 1, 0),
                B9D.canonical_key(5, 0, 0, -1), B9D.canonical_key(4, 9, 9, 9)]
        self.assertEqual(sorted(keys), [(4, 9, 9, 9), (5, 0, 0, -1), (5, 0, 1, -1), (5, 0, 1, 0)])


class ClassificationTests(unittest.TestCase):
    """§7 as amended: target programs fail visibly on unknowns; non-targets stay non-targets."""

    def setUp(self):
        self.idl = {"instructions": [{"name": "buy"}, {"name": "sell"}, {"name": "create"}]}
        self.maps = {B9D.PUMP_PROGRAM: B9D.idl_instruction_map(self.idl)}

    def discriminator_for(self, name):
        return hashlib.sha256(f"global:{name}".encode()).digest()[:8]

    def test_discriminators_derive_from_the_pinned_idl_not_a_hardcoded_list(self):
        mapping = B9D.idl_instruction_map(self.idl)
        self.assertEqual(mapping[self.discriminator_for("buy").hex()], "buy")
        self.assertEqual(len(mapping), 3)

    def test_an_empty_idl_is_refused(self):
        with self.assertRaises(B9D.FreezeViolation):
            B9D.idl_instruction_map({"instructions": []})

    def test_a_known_target_instruction_resolves(self):
        data = self.discriminator_for("sell") + b"\x00" * 16
        target, name, disc, reason = B9D.classify_instruction(B9D.PUMP_PROGRAM, data, self.maps)
        self.assertEqual((target, name, reason), (True, "sell", None))
        self.assertEqual(disc, self.discriminator_for("sell").hex())

    def test_an_unknown_target_discriminator_fails_visibly(self):
        data = bytes(range(8)) + b"\x00" * 4
        target, name, disc, reason = B9D.classify_instruction(B9D.PUMP_PROGRAM, data, self.maps)
        self.assertTrue(target)
        self.assertIsNone(name)
        self.assertEqual(disc, bytes(range(8)).hex())
        self.assertIn("unknown", reason)
        self.assertIn("not bucketed as 'other'", reason)

    def test_a_non_target_program_is_preserved_not_decoded_as_pump(self):
        """Seq 198: B9d must not pretend a third-party program shares a Pump IDL."""
        data = self.discriminator_for("buy") + b"\x00" * 8
        target, name, disc, reason = B9D.classify_instruction(
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", data, self.maps)
        self.assertEqual((target, name, disc, reason), (False, None, None, None),
                         "a colliding discriminator on another program must not resolve to 'buy'")

    def test_target_data_too_short_to_carry_a_discriminator_fails(self):
        target, name, disc, reason = B9D.classify_instruction(B9D.PUMP_PROGRAM, b"\x01", self.maps)
        self.assertTrue(target)
        self.assertIsNone(name)
        self.assertIn("too short", reason)

    def test_pumpswap_is_a_target_program(self):
        self.assertIn(B9D.PUMPSWAP_PROGRAM, B9D.TARGET_PROGRAMS)
        self.assertIn(B9D.PUMP_PROGRAM, B9D.TARGET_PROGRAMS)


class ArtifactTests(unittest.TestCase):
    """§5: schema, resume, and the immutability B9b's Seq 188 correction exists for."""

    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "b9d.sqlite"

    def artifact(self):
        database = B9D.connect(str(self.path))
        B9D.schema(database)
        return database

    def test_schema_creates_every_table_the_freeze_requires(self):
        database = self.artifact()
        names = {row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for required in ("metadata", "raw_transaction", "raw_block_signatures",
                         "transaction_coordinate", "instruction", "reserve_observation",
                         "classification_failure"):
            self.assertIn(required, names)
        database.close()

    def test_a_completed_artifact_can_never_be_overwritten(self):
        database = self.artifact()
        database.execute("INSERT INTO metadata VALUES ('completed_at_unix','1')")
        self.assertEqual(B9D.artifact_state(database), "complete")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.refuse_if_complete(database)
        self.assertIn("never be overwritten", str(ctx.exception))
        database.close()

    def test_a_partial_artifact_is_resumable_and_not_refused(self):
        database = self.artifact()
        database.execute("INSERT INTO metadata VALUES ('started_at_unix','1')")
        self.assertEqual(B9D.artifact_state(database), "partial")
        self.assertIsNone(B9D.refuse_if_complete(database))
        database.close()

    def test_resume_across_a_changed_source_is_refused(self):
        database = self.artifact()
        database.execute("INSERT INTO metadata VALUES ('b9c_sha256','deadbeef')")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_resumable(database, {B9D.B9C_PATH: B9D.B9C_SHA256})
        self.assertIn("refusing to resume", str(ctx.exception))
        database.close()

    def test_resume_with_matching_sources_is_allowed(self):
        database = self.artifact()
        database.execute("INSERT INTO metadata VALUES ('b9c_sha256',?)", (B9D.B9C_SHA256,))
        self.assertTrue(B9D.assert_resumable(database, {B9D.B9C_PATH: B9D.B9C_SHA256}))
        database.close()

    def test_a_coordinate_cannot_be_claimed_by_two_signatures(self):
        database = self.artifact()
        database.execute("INSERT INTO raw_block_signatures VALUES (7,'getBlock','[]',0,'h',x'00')")
        database.execute("INSERT INTO transaction_coordinate VALUES ('a',7,0)")
        with self.assertRaises(sqlite3.IntegrityError):
            database.execute("INSERT INTO transaction_coordinate VALUES ('b',7,0)")
        database.close()

    def test_two_instructions_cannot_share_a_canonical_key(self):
        database = self.artifact()
        row = (5, 0, 1, -1, "sig", B9D.PUMP_PROGRAM, "aa", "buy", 1, "[]", 24)
        database.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        with self.assertRaises(sqlite3.IntegrityError):
            database.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        database.close()


class ExecutionGateTests(unittest.TestCase):
    """§10: the gate must be a hard stop in code, not a sentence in a document."""

    def test_run_refuses_and_names_the_authorisation_it_lacks(self):
        with self.assertRaises(SystemExit) as ctx:
            B9D.main(["run"])
        message = str(ctx.exception)
        self.assertIn("NOT authorised", message)
        self.assertIn("94,985", message)
        self.assertIn("38,853", message)
        self.assertIn("133,838", message)

    def test_the_module_issues_no_network_calls_at_all(self):
        """A scaffold that imports an HTTP client is one edit away from being runnable."""
        source = (ROOT / "scripts" / "b9d_transaction_bodies.py").read_text()
        for forbidden in ("urllib.request", "urlopen", "requests.", "http.client", "socket."):
            self.assertNotIn(forbidden, source,
                             f"{forbidden} must not appear in the gated scaffold")

    def test_verify_is_offline_and_init_creates_an_artifact(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(B9D.main(["init", str(directory / "a.sqlite")]), 0)
        database = sqlite3.connect(directory / "a.sqlite")
        names = {row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        database.close()
        self.assertIn("raw_block_signatures", names)


if __name__ == "__main__":
    unittest.main()
