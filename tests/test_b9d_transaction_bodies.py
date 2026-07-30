"""Offline tests for the B9d scaffold.

Every test here runs with no network and no dependency on the 840 MiB B9c artifact: the population
logic is exercised against small synthetic databases built to the same schema. The real artifact is
asserted at run time by `verify`, which is where a mismatch must stop a run — a unit test that
streams 1.35M rows would move that check into the suite and slow it into disuse.
"""
import base64
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
import zlib

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


class BoundaryCoverageTests(unittest.TestCase):
    """§4: interface coverage over the observation range is measured, never inherited.

    B0 puts the last Pump deploy 798,662 slots before the window opens, but B0 ran ~2 h before the
    cutoff slot's block time and its ProgramData history has unverified archival completeness. So
    the artifact carries the check.
    """

    PROGRAM = "TestProgram1111111111111111111111111111111"

    def covered(self, low, high, **overrides):
        row = {"program_id": self.PROGRAM, "from_slot": low, "to_slot": high,
               "idl_path": "research/x.json", "idl_sha256": "a" * 64,
               "deploy_slot": low - 1, "evidence_key": "getAccountInfo:1",
               "coverage": "covered"}
        row.update(overrides)
        return row

    def test_the_frozen_range_is_the_freeze_range_not_the_population_range(self):
        """SLOT_MAX is only the newest slot the population occupies; the range runs to the cutoff."""
        self.assertEqual(B9D.OBSERVATION_RANGE, (433_894_233, 435_536_742))
        self.assertEqual(B9D.CUTOFF_SLOT, 435_536_742)
        self.assertGreater(B9D.CUTOFF_SLOT, B9D.SLOT_MAX)

    def test_a_fully_tiled_covered_range_passes(self):
        low, high = B9D.OBSERVATION_RANGE
        rows = B9D.assert_boundary_coverage(self.PROGRAM, [self.covered(low, high)])
        self.assertEqual(len(rows), 1)

    def test_a_gap_inside_the_range_is_refused_and_named(self):
        low, high = B9D.OBSERVATION_RANGE
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_boundary_coverage(
                self.PROGRAM, [self.covered(low, high - 100)])
        self.assertIn("no boundary evidence covers", str(ctx.exception))
        self.assertIn(f"{high - 99:,}", str(ctx.exception))

    def test_an_uncovered_interval_overlapping_the_range_is_refused(self):
        low, high = B9D.OBSERVATION_RANGE
        rows = [self.covered(low, low + 10),
                {"program_id": self.PROGRAM, "from_slot": low + 11, "to_slot": high,
                 "idl_path": None, "idl_sha256": None, "deploy_slot": None,
                 "evidence_key": "k", "coverage": "uncovered"}]
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_boundary_coverage(self.PROGRAM, rows)
        self.assertIn("version-aware decoder", str(ctx.exception))

    def test_overlapping_intervals_are_refused(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.validate_intervals(self.PROGRAM,
                                   [self.covered(100, 200), self.covered(150, 300)])
        self.assertIn("overlap", str(ctx.exception))

    def test_a_covered_interval_without_its_evidence_is_refused(self):
        for field in ("idl_path", "idl_sha256", "evidence_key"):
            with self.assertRaises(B9D.FreezeViolation) as ctx:
                B9D.validate_intervals(self.PROGRAM, [self.covered(100, 200, **{field: None})])
            self.assertIn(field, str(ctx.exception))

    def test_an_uncovered_interval_may_not_name_a_revision(self):
        """Otherwise an evidence gap sits in the table looking exactly like a decodable interval."""
        row = self.covered(100, 200, coverage="uncovered")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.validate_intervals(self.PROGRAM, [row])
        self.assertIn("must not look decodable", str(ctx.exception))

    def test_resolve_returns_the_interval_in_force(self):
        rows = [self.covered(100, 200), self.covered(201, 300, idl_sha256="b" * 64)]
        self.assertEqual(B9D.resolve_version(self.PROGRAM, 250, rows)["idl_sha256"], "b" * 64)
        self.assertEqual(B9D.resolve_version(self.PROGRAM, 100, rows)["idl_sha256"], "a" * 64)

    def test_a_slot_outside_every_interval_is_not_attributed_to_the_nearest(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.resolve_version(self.PROGRAM, 999, [self.covered(100, 200)])
        self.assertIn("nearest pinned revision", str(ctx.exception))

    def test_resolving_inside_an_uncovered_interval_is_refused(self):
        row = {"program_id": self.PROGRAM, "from_slot": 100, "to_slot": 200, "idl_path": None,
               "idl_sha256": None, "deploy_slot": None, "evidence_key": "k",
               "coverage": "uncovered"}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.resolve_version(self.PROGRAM, 150, [row])
        self.assertIn("refusing to decode", str(ctx.exception))


class BoundaryEvidenceDerivationTests(unittest.TestCase):
    """The one case that yields coverage is the freeze's own argument, and only that case."""

    PROGRAM = "TestProgram1111111111111111111111111111111"
    LOW, HIGH = B9D.OBSERVATION_RANGE

    def derive(self, last_deploy, in_range=(), **kwargs):
        return B9D.intervals_from_boundary_evidence(
            self.PROGRAM, last_deploy, list(in_range), "research/x.json", "a" * 64,
            "getAccountInfo:1", **kwargs)

    def test_a_last_deploy_before_the_range_covers_it_from_current_state_alone(self):
        """Since it is the most recent deployment ever, none happened inside the range."""
        rows = self.derive(self.LOW - 798_662)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["coverage"], "covered")
        self.assertEqual((rows[0]["from_slot"], rows[0]["to_slot"]), (self.LOW, self.HIGH))
        self.assertEqual(B9D.assert_boundary_coverage(self.PROGRAM, rows), rows)

    def test_the_real_pump_deploy_slot_covers_the_frozen_range(self):
        """B0's measured last Pump deploy, checked against the frozen range arithmetic."""
        rows = self.derive(433_095_571)
        self.assertEqual(rows[0]["coverage"], "covered")
        self.assertEqual(self.LOW - 433_095_571, 798_662)

    def test_a_deploy_after_the_range_start_cannot_be_settled_by_current_state(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.derive(self.LOW + 5)
        self.assertIn("loader history", str(ctx.exception))

    def test_a_deploy_after_the_whole_range_still_yields_no_coverage(self):
        """The build running during the range was an earlier one; today's pin is unattributed.

        This is the subtle case: no boundary sits inside the range, so a lenient implementation
        would call it covered. It is not — the revision in force then was not necessarily the
        revision retrieved now.
        """
        rows = self.derive(self.HIGH + 1_000, history_complete=True)
        self.assertTrue(rows)
        self.assertTrue(all(row["coverage"] == "uncovered" for row in rows))
        with self.assertRaises(B9D.FreezeViolation):
            B9D.assert_boundary_coverage(self.PROGRAM, rows)

    def test_an_in_range_deploy_splits_the_range_and_covers_nothing(self):
        edge = self.LOW + 1_000
        rows = self.derive(self.HIGH + 1, in_range=[edge], history_complete=True)
        self.assertEqual([(r["from_slot"], r["to_slot"]) for r in rows],
                         [(self.LOW, edge - 1), (edge, self.HIGH)])
        self.assertTrue(all(r["coverage"] == "uncovered" for r in rows))

    def test_contradictory_evidence_is_refused_rather_than_reconciled(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.derive(self.LOW - 10, in_range=[self.LOW + 5])
        self.assertIn("contradict", str(ctx.exception))

    def test_a_deploy_slot_outside_the_range_cannot_be_passed_as_in_range(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.derive(self.HIGH + 1, in_range=[self.HIGH + 500], history_complete=True)
        self.assertIn("outside", str(ctx.exception))

    def test_the_schema_carries_boundary_evidence_and_the_version_map(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "b9d.sqlite"
        database = B9D.connect(str(path))
        B9D.schema(database)
        names = {row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        database.close()
        self.assertIn("raw_boundary_response", names)
        self.assertIn("program_version", names)


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


class PinnedDecoderTests(unittest.TestCase):
    """Offline decoder is bound to the exact local IDL and consumes payloads exactly."""

    @classmethod
    def setUpClass(cls):
        cls.idl = B9D.load_pinned_idl(
            str(ROOT / B9D.PUMP_IDL_PATH), B9D.PUMP_IDL_SHA256, B9D.PUMP_PROGRAM)

    def instruction(self, name):
        return next(entry for entry in self.idl["instructions"] if entry["name"] == name)

    def test_real_pump_idl_is_exactly_pinned(self):
        self.assertEqual(self.idl["address"], B9D.PUMP_PROGRAM)
        self.assertEqual(B9D.sha256_file(str(ROOT / B9D.PUMP_IDL_PATH)), B9D.PUMP_IDL_SHA256)

    def test_a_changed_idl_is_refused(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "idl.json"
        path.write_text(json.dumps(self.idl) + "\n")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.load_pinned_idl(str(path), B9D.PUMP_IDL_SHA256, B9D.PUMP_PROGRAM)
        self.assertIn("interface drift", str(ctx.exception))

    def test_declared_discriminator_is_authoritative(self):
        custom = {"instructions": [{"name": "buy", "discriminator": list(range(8))}]}
        self.assertEqual(B9D.idl_instruction_map(custom), {bytes(range(8)).hex(): "buy"})

    def test_real_sell_arguments_and_accounts_decode(self):
        entry = self.instruction("sell")
        data = bytes(entry["discriminator"]) + (7).to_bytes(8, "little") + (9).to_bytes(8, "little")
        account_count = len(B9D.flatten_accounts(entry["accounts"]))
        keys = [f"account-{index}" for index in range(account_count)] + ["remaining"]
        decoded = B9D.decode_idl_instruction(self.idl, data, keys)
        self.assertEqual(decoded["name"], "sell")
        self.assertEqual(decoded["args"], {"amount": 7, "min_sol_output": 9})
        self.assertEqual(decoded["accounts"]["global"], "account-0")
        self.assertEqual(decoded["remaining_accounts"], ["remaining"])

    def test_real_buy_defined_option_bool_decodes(self):
        entry = self.instruction("buy")
        data = (bytes(entry["discriminator"]) + (3).to_bytes(8, "little") +
                (4).to_bytes(8, "little") + b"\x01")
        keys = [f"a{index}" for index in range(len(B9D.flatten_accounts(entry["accounts"])))]
        decoded = B9D.decode_idl_instruction(self.idl, data, keys)
        self.assertEqual(decoded["args"],
                         {"amount": 3, "max_sol_cost": 4, "track_volume": [True]})

    def test_instruction_trailing_bytes_fail_exact_consumption(self):
        entry = self.instruction("sell")
        data = bytes(entry["discriminator"]) + b"\0" * 17
        keys = ["a"] * len(B9D.flatten_accounts(entry["accounts"]))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.decode_idl_instruction(self.idl, data, keys)
        self.assertIn("unconsumed", str(ctx.exception))

    def test_complete_event_decodes_from_real_layout(self):
        event = next(entry for entry in self.idl["events"] if entry["name"] == "CompleteEvent")
        pubkeys = [bytes([value]) * 32 for value in (1, 2, 3, 4)]
        payload = (bytes(event["discriminator"]) + pubkeys[0] + pubkeys[1] + pubkeys[2] +
                   (-5).to_bytes(8, "little", signed=True) + pubkeys[3])
        name, decoded = B9D.decode_idl_event(self.idl, payload)
        self.assertEqual(name, "CompleteEvent")
        self.assertEqual(decoded["timestamp"], -5)
        self.assertEqual(decoded["user"], B9D.base58(pubkeys[0]))
        self.assertEqual(decoded["quote_mint"], B9D.base58(pubkeys[3]))

    def test_trade_event_reserve_projection_is_exact_and_named(self):
        fields = {"virtual_quote_reserves": 1, "virtual_token_reserves": 2,
                  "real_quote_reserves": 3, "real_token_reserves": 4, "ignored": 5}
        self.assertEqual(B9D.reserve_after_from_event("TradeEvent", fields), {
            "virtual_quote_reserves": 1, "virtual_token_reserves": 2,
            "real_quote_reserves": 3, "real_token_reserves": 4})
        self.assertIsNone(B9D.reserve_after_from_event("CompleteEvent", fields))

    def test_pump_candidates_are_derived_from_writable_curve_accounts(self):
        candidates = B9D.reserve_mutation_candidates(B9D.PUMP_PROGRAM, self.idl)
        self.assertIn("buy", candidates)
        self.assertIn("migrate", candidates)
        self.assertIn("set_mayhem_virtual_params", candidates)
        self.assertNotIn("get_minimum_distributable_fee", candidates)
        self.assertEqual(candidates["set_mayhem_virtual_params"], ("bonding_curve",))

    def test_non_trade_writable_candidate_cannot_be_cleared_by_event_absence(self):
        candidates = {B9D.PUMP_PROGRAM:
                      B9D.reserve_mutation_candidates(B9D.PUMP_PROGRAM, self.idl)}
        plan = B9D.reserve_extraction_plan(
            B9D.PUMP_PROGRAM, "set_mayhem_virtual_params", candidates)
        self.assertTrue(plan["candidate"])
        self.assertIsNone(plan["event_projection"])
        self.assertTrue(plan["reconciliation_required"])

    def test_trade_event_projection_does_not_waive_reconciliation(self):
        candidates = {B9D.PUMP_PROGRAM:
                      B9D.reserve_mutation_candidates(B9D.PUMP_PROGRAM, self.idl)}
        plan = B9D.reserve_extraction_plan(B9D.PUMP_PROGRAM, "buy", candidates)
        self.assertEqual(plan["event_projection"], "TradeEvent")
        self.assertTrue(plan["reconciliation_required"])

    def test_a_partial_target_map_is_still_refused(self):
        """The gap Codex left visible in Seq 202 must stay refusable now that it is filled.

        A missing IDL must never be able to masquerade as a run full of unknown-discriminator
        failures, which would look like a finding about the chain rather than about the decoder.
        """
        pump_map = {B9D.PUMP_PROGRAM: B9D.idl_instruction_map(self.idl)}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.require_all_target_idls(pump_map)
        self.assertIn(B9D.PUMPSWAP_PROGRAM, str(ctx.exception))


class PinnedPumpSwapIdlTests(unittest.TestCase):
    """The PumpSwap interface is retrieved and pinned, never invented (AGENTS.md).

    Source: `pump-fun/pump-public-docs` `idl/pump_amm.json` at commit
    `9c82f61cb711b044a17f770ab8ce9f9bdf78f333`, retrieved 2026-07-29 — the same commit the Pump
    IDL is pinned at and the one `research/B0_PUMPSWAP_PROGRAM_UPGRADE_INVENTORY.md` cites.
    """

    def setUp(self):
        self.path = ROOT / B9D.PUMPSWAP_IDL_PATH
        self.idl = json.loads(self.path.read_bytes())

    def test_the_pinned_file_is_present_and_hashes_to_its_recorded_value(self):
        self.assertTrue(self.path.exists(), "the pinned IDL must be committed, not fetched at run time")
        self.assertEqual(B9D.sha256_file(str(self.path)), B9D.PUMPSWAP_IDL_SHA256)

    def test_it_declares_the_expected_program_address(self):
        self.assertEqual(self.idl["address"], B9D.PUMPSWAP_PROGRAM)
        self.assertEqual(self.idl["metadata"]["name"], "pump_amm")

    def test_hash_or_address_drift_fails_closed(self):
        with self.assertRaises(B9D.FreezeViolation):
            B9D.load_pinned_idl(str(self.path), "0" * 64, B9D.PUMPSWAP_PROGRAM)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.load_pinned_idl(str(self.path), B9D.PUMPSWAP_IDL_SHA256, B9D.PUMP_PROGRAM)
        self.assertIn("declares", str(ctx.exception))

    def test_every_declared_discriminator_matches_the_anchor_derivation(self):
        """Two independent derivations agreeing is what separates a retrieved IDL from a guess."""
        for entry in self.idl["instructions"]:
            derived = list(hashlib.sha256(f"global:{entry['name']}".encode()).digest()[:8])
            self.assertEqual(entry["discriminator"], derived, entry["name"])
        events = [e for e in self.idl.get("events", []) if "discriminator" in e]
        self.assertTrue(events)
        for entry in events:
            derived = list(hashlib.sha256(f"event:{entry['name']}".encode()).digest()[:8])
            self.assertEqual(entry["discriminator"], derived, entry["name"])

    def test_the_instruction_map_is_complete_and_unambiguous(self):
        mapping = B9D.idl_instruction_map(self.idl)
        self.assertEqual(len(mapping), len(self.idl["instructions"]),
                         "a collision would have been silently deduplicated")
        self.assertEqual(len(mapping), 31)

    def test_pumpswap_candidates_include_non_trade_vault_mutations(self):
        candidates = B9D.reserve_mutation_candidates(B9D.PUMPSWAP_PROGRAM, self.idl)
        self.assertIn("deposit", candidates)
        self.assertIn("withdraw", candidates)
        self.assertIn("boost_buy_and_burn", candidates)
        self.assertIn("migrate_pool_coin_creator", candidates)
        self.assertEqual(candidates["migrate_pool_coin_creator"], ("pool",))
        self.assertEqual(
            candidates["boost_buy_and_burn"],
            ("pool_base_token_account", "pool_quote_token_account"))

    def test_pumpswap_non_trade_requires_reconciliation_without_trade_projection(self):
        candidates = {B9D.PUMPSWAP_PROGRAM:
                      B9D.reserve_mutation_candidates(B9D.PUMPSWAP_PROGRAM, self.idl)}
        plan = B9D.reserve_extraction_plan(B9D.PUMPSWAP_PROGRAM, "deposit", candidates)
        self.assertEqual(plan["writable_roles"],
                         ("pool", "pool_base_token_account", "pool_quote_token_account"))
        self.assertIsNone(plan["event_projection"])
        self.assertTrue(plan["reconciliation_required"])

    def test_target_maps_cover_both_programs_and_are_not_swapped(self):
        """`sell` and `buy` exist in BOTH IDLs with identical discriminators.

        An earlier version of this test classified `sell` and passed whether or not
        `target_idl_maps` loaded the Pump IDL for the PumpSwap program — a mutation proved it. The
        13 shared names are exactly the ones that cannot distinguish the two maps, so the
        assertions below use instructions unique to each side.
        """
        maps = B9D.target_idl_maps(str(ROOT / B9D.PUMP_IDL_PATH), str(self.path))
        self.assertEqual(set(maps), set(B9D.TARGET_PROGRAMS))
        self.assertTrue(B9D.require_all_target_idls(maps))
        self.assertNotEqual(maps[B9D.PUMP_PROGRAM], maps[B9D.PUMPSWAP_PROGRAM],
                            "identical maps would mean one IDL was loaded for both programs")
        self.assertIn("create_pool", maps[B9D.PUMPSWAP_PROGRAM].values())
        self.assertNotIn("create_pool", maps[B9D.PUMP_PROGRAM].values())
        self.assertIn("migrate", maps[B9D.PUMP_PROGRAM].values())
        self.assertNotIn("migrate", maps[B9D.PUMPSWAP_PROGRAM].values())

    def test_a_pumpswap_only_instruction_classifies_against_its_own_idl(self):
        maps = B9D.target_idl_maps(str(ROOT / B9D.PUMP_IDL_PATH), str(self.path))
        entry = next(i for i in self.idl["instructions"] if i["name"] == "create_pool")
        data = bytes(entry["discriminator"]) + b"\x00" * 16
        target, name, disc, reason = B9D.classify_instruction(B9D.PUMPSWAP_PROGRAM, data, maps)
        self.assertEqual((target, name, reason), (True, "create_pool", None))
        self.assertEqual(disc, bytes(entry["discriminator"]).hex())
        # The same bytes on the Pump program must NOT resolve: it has no such instruction.
        target, name, _, reason = B9D.classify_instruction(B9D.PUMP_PROGRAM, data, maps)
        self.assertTrue(target)
        self.assertIsNone(name)
        self.assertIn("unknown", reason)

    def test_a_declared_discriminator_collision_is_refused_not_deduplicated(self):
        """The real IDL has no collision, so only a synthetic one can exercise the guard.

        Without this, removing the collision check changed nothing observable: the completeness
        assertion `len(map) == len(instructions)` holds trivially when no two entries collide.
        """
        shared = list(hashlib.sha256(b"global:buy").digest()[:8])
        colliding = {"instructions": [{"name": "buy", "discriminator": shared},
                                      {"name": "sell", "discriminator": shared}]}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.idl_instruction_map(colliding)
        self.assertIn("collision", str(ctx.exception))

    def test_an_unknown_pumpswap_discriminator_still_fails_visibly(self):
        maps = B9D.target_idl_maps(str(ROOT / B9D.PUMP_IDL_PATH), str(self.path))
        target, name, disc, reason = B9D.classify_instruction(
            B9D.PUMPSWAP_PROGRAM, bytes(range(8)) + b"\x00", maps)
        self.assertTrue(target)
        self.assertIsNone(name)
        self.assertIn("unknown", reason)

    def test_the_manifest_records_provenance_not_just_a_hash(self):
        manifest = B9D.decoder_manifest(str(ROOT / B9D.PUMP_IDL_PATH), str(self.path))
        self.assertEqual(manifest["pumpswap_idl_sha256"], B9D.PUMPSWAP_IDL_SHA256)
        self.assertEqual(manifest["pumpswap_program"], B9D.PUMPSWAP_PROGRAM)
        self.assertEqual(manifest["idl_source_commit"], "9c82f61cb711b044a17f770ab8ce9f9bdf78f333")
        self.assertEqual(manifest["idl_access_date"], "2026-07-29")
        self.assertNotIn("pumpswap_idl_status", manifest,
                         "the MISSING_PINNED_IDL hard-failure marker must be gone, not falsified")


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

    def test_a_completed_rerun_is_byte_immutable_and_makes_zero_rpc_calls(self):
        """§11 at the production call site, including the ordering of the refusal.

        The completed marker must be discovered through a read-only open before source scans,
        population derivation, writable SQLite pragmas, or an RPC request can occur.
        """
        database = self.artifact()
        with database:
            database.execute("INSERT INTO metadata VALUES ('completed_at_unix','1')")
        database.close()
        before = B9D.sha256_file(self.path)
        touched = []
        saved = (B9D.assert_sources, B9D.frozen_population_by_slot, B9D.rpc_request)

        def forbidden(name):
            def call(*args, **kwargs):
                touched.append(name)
                raise AssertionError(f"completed rerun reached forbidden {name}")
            return call

        B9D.assert_sources = forbidden("source scan")
        B9D.frozen_population_by_slot = forbidden("population scan")
        B9D.rpc_request = forbidden("RPC")
        self.addCleanup(lambda: setattr(B9D, "assert_sources", saved[0]))
        self.addCleanup(lambda: setattr(B9D, "frozen_population_by_slot", saved[1]))
        self.addCleanup(lambda: setattr(B9D, "rpc_request", saved[2]))

        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.collect_raw_population("https://unused.invalid", str(self.path))
        self.assertIn("already marked complete", str(ctx.exception))
        self.assertEqual(touched, [])
        self.assertEqual(B9D.sha256_file(self.path), before)

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

    def test_coordinate_phase_refuses_a_silently_short_population(self):
        database = self.artifact()
        database.execute("INSERT INTO raw_block_signatures VALUES (7,'getBlock','[]',0,'h',x'00')")
        database.execute("INSERT INTO transaction_coordinate VALUES ('a',7,0)")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.transaction_body_coordinates(database)
        self.assertIn("1/38,853 block signature lists", str(ctx.exception))
        self.assertIn("1/94,985 transaction coordinates", str(ctx.exception))
        self.assertIn("refusing to start transaction-body collection", str(ctx.exception))
        database.close()

    def test_coordinate_phase_accepts_the_exact_frozen_shape(self):
        database = self.artifact()
        database.execute("INSERT INTO raw_block_signatures VALUES (7,'getBlock','[]',0,'h',x'00')")
        database.executemany(
            "INSERT INTO transaction_coordinate VALUES (?,?,?)", (("a", 7, 0), ("b", 7, 1)))
        self.assertTrue(B9D.assert_coordinate_population(
            database, expected_slots=1, expected_signatures=2))
        self.assertEqual(B9D.transaction_body_coordinates(database, require_complete=False),
                         [("a", 7), ("b", 7)])
        database.close()

    def test_raw_body_phase_refuses_a_silently_short_population(self):
        database = self.artifact()
        B9D.store_raw(database, "raw_transaction", "signature", "a",
                      "getTransaction", ["a"], b"one", received_at=1)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_raw_transaction_population(database, expected_signatures=2)
        self.assertIn("1/2 transaction bodies", str(ctx.exception))
        self.assertIn("refusing to make the artifact available for decoding", str(ctx.exception))
        database.close()

    def test_raw_body_phase_accepts_the_exact_population(self):
        database = self.artifact()
        for signature in ("a", "b"):
            B9D.store_raw(database, "raw_transaction", "signature", signature,
                          "getTransaction", [signature], signature.encode(), received_at=1)
        self.assertTrue(B9D.assert_raw_transaction_population(database, expected_signatures=2))
        database.close()

    def test_two_instructions_cannot_share_a_canonical_key(self):
        database = self.artifact()
        row = (5, 0, 1, -1, "sig", B9D.PUMP_PROGRAM, "aa", "buy", 1, "[]", 24)
        database.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        with self.assertRaises(sqlite3.IntegrityError):
            database.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        database.close()


def short_vec(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def build_transaction(keys, instructions, version="legacy", lookups=()):
    """Serialise a minimal but wire-correct transaction. `keys` are 32-byte blobs."""
    body = bytearray()
    body += short_vec(1) + b"\x11" * 64                     # one signature
    if version != "legacy":
        body.append(0x80 | version)
    body += bytes((1, 0, 0))                                 # header
    body += short_vec(len(keys)) + b"".join(keys)
    body += b"\x22" * 32                                     # recent blockhash
    body += short_vec(len(instructions))
    for program_index, accounts, data in instructions:
        body.append(program_index)
        body += short_vec(len(accounts)) + bytes(accounts)
        body += short_vec(len(data)) + data
    if version != "legacy":
        body += short_vec(len(lookups))
        for writable, readonly in lookups:
            body += b"\x33" * 32
            body += short_vec(len(writable)) + bytes(writable)
            body += short_vec(len(readonly)) + bytes(readonly)
    return bytes(body)


def as_result(raw, meta=None, version="legacy", slot=1):
    return {"slot": slot, "version": version, "meta": meta or {},
            "transaction": [base64.b64encode(raw).decode(), "base64"]}


class EnvelopeParsingTests(unittest.TestCase):
    """§7's prerequisite. Nothing could classify instructions because nothing produced any.

    Validated against **3,923 real preserved bodies, all parsing with zero failures** across 2,583
    v0 and 1,340 legacy transactions, resolving to genuine known program ids (System, Token-2022,
    Pump, ComputeBudget, ATA). A misaligned account index yields garbage addresses, not the ATA
    program, so that resolution is evidence and not merely absence of an exception. These tests pin
    the boundaries that real data happened not to exercise.
    """

    KEY_A = bytes(range(32))
    KEY_B = bytes(range(32, 64))

    def test_compact_u16_covers_all_three_widths(self):
        for value in (0, 1, 127, 128, 16383, 16384, 65535):
            data = short_vec(value) + b"tail"
            parsed, offset = B9D.compact_u16(data, 0)
            self.assertEqual(parsed, value)
            self.assertEqual(data[offset:], b"tail")

    def test_a_truncated_or_overlong_length_prefix_fails(self):
        with self.assertRaises(B9D.FreezeViolation):
            B9D.compact_u16(b"\x80", 0)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.compact_u16(b"\x80\x80\x80\x80", 0)
        self.assertIn("three bytes", str(ctx.exception))

    def test_base58_decode_inverts_the_encoder_including_leading_zeros(self):
        for raw in (b"", b"\x00", b"\x00\x00\x01", bytes(range(32)), b"\xff" * 8):
            self.assertEqual(B9D.base58_decode(B9D.base58(raw)), raw)

    def test_an_invalid_base58_character_fails_visibly(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.base58_decode("0OIl")            # the four characters base58 excludes
        self.assertIn("invalid base58", str(ctx.exception))

    def test_a_legacy_transaction_parses_to_its_instructions(self):
        raw = build_transaction([self.KEY_A, self.KEY_B], [(0, [1], b"\x01\x02")])
        rows = B9D.envelope_instructions(as_result(raw))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["program_id"], B9D.base58(self.KEY_A))
        self.assertEqual(rows[0]["accounts"], [B9D.base58(self.KEY_B)])
        self.assertEqual(rows[0]["data"], b"\x01\x02")
        self.assertEqual((rows[0]["outer_index"], rows[0]["inner_index"]), (0, -1))

    def test_a_v0_transaction_resolves_loaded_addresses_after_the_static_keys(self):
        raw = build_transaction([self.KEY_A], [(1, [2], b"\x09")],
                                version=0, lookups=[([7], [9])])
        meta = {"loadedAddresses": {"writable": ["WritableAddr"], "readonly": ["ReadonlyAddr"]}}
        rows = B9D.envelope_instructions(as_result(raw, meta, version=0))
        self.assertEqual(rows[0]["program_id"], "WritableAddr",
                         "index 1 must be the first loaded WRITABLE address, not the readonly one")
        self.assertEqual(rows[0]["accounts"], ["ReadonlyAddr"])

    def test_a_lookup_count_disagreeing_with_meta_is_refused(self):
        """A misaligned resolution shifts every index past the static keys."""
        raw = build_transaction([self.KEY_A], [(0, [], b"")], version=0, lookups=[([7, 8], [9])])
        meta = {"loadedAddresses": {"writable": ["one"], "readonly": []}}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.envelope_instructions(as_result(raw, meta, version=0))
        self.assertIn("misaligned", str(ctx.exception))

    def test_trailing_bytes_after_the_message_are_fatal(self):
        raw = build_transaction([self.KEY_A], [(0, [], b"")]) + b"\x00extra"
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.parse_message(raw)
        self.assertIn("remain after parsing", str(ctx.exception))

    def test_an_unresolvable_program_index_is_refused(self):
        raw = build_transaction([self.KEY_A], [(9, [], b"")])
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.envelope_instructions(as_result(raw))
        self.assertIn("outside the 1 resolved account keys", str(ctx.exception))

    def test_inner_instructions_are_base58_and_sort_after_their_outer(self):
        raw = build_transaction([self.KEY_A, self.KEY_B],
                                [(0, [], b"\xaa"), (0, [], b"\xbb")])
        meta = {"innerInstructions": [
            {"index": 0, "instructions": [
                {"programIdIndex": 1, "accounts": [0], "data": B9D.base58(b"\x00\x07")}]}]}
        rows = B9D.envelope_instructions(as_result(raw, meta))
        self.assertEqual([(r["outer_index"], r["inner_index"]) for r in rows],
                         [(0, -1), (0, 0), (1, -1)])
        self.assertEqual(rows[1]["data"], b"\x00\x07",
                         "inner data is base58; decoding it as base64 would yield garbage")
        self.assertEqual(rows[1]["program_id"], B9D.base58(self.KEY_B))

    def test_an_inner_group_for_a_nonexistent_outer_index_is_refused(self):
        raw = build_transaction([self.KEY_A], [(0, [], b"")])
        meta = {"innerInstructions": [{"index": 5, "instructions": []}]}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.envelope_instructions(as_result(raw, meta))
        self.assertIn("does not contain", str(ctx.exception))

    def test_a_non_base64_encoding_tag_is_refused(self):
        raw = build_transaction([self.KEY_A], [(0, [], b"")])
        result = as_result(raw)
        result["transaction"] = [base64.b64encode(raw).decode(), "base58"]
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.envelope_instructions(result)
        self.assertIn("frozen encoding is base64", str(ctx.exception))

    def test_canonical_keys_order_a_whole_transaction_correctly(self):
        raw = build_transaction([self.KEY_A, self.KEY_B],
                                [(0, [], b"\x01"), (1, [], b"\x02")])
        meta = {"innerInstructions": [
            {"index": 1, "instructions": [
                {"programIdIndex": 0, "accounts": [], "data": B9D.base58(b"\x03")},
                {"programIdIndex": 0, "accounts": [], "data": B9D.base58(b"\x04")}]}]}
        rows = B9D.envelope_instructions(as_result(raw, meta))
        keys = [B9D.canonical_key(7, 3, r["outer_index"], r["inner_index"]) for r in rows]
        self.assertEqual(keys, sorted(keys), "envelope order must already be canonical order")


class DecoderOrchestrationTests(unittest.TestCase):
    """Complete raw bodies become one canonical, fail-visible instruction stream."""

    SLOT = B9D.SLOT_MIN

    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "decode.sqlite"
        self.database = B9D.connect(str(self.path))
        B9D.schema(self.database)
        self.addCleanup(self.database.close)
        for program, path, digest in (
                (B9D.PUMP_PROGRAM, B9D.PUMP_IDL_PATH, B9D.PUMP_IDL_SHA256),
                (B9D.PUMPSWAP_PROGRAM, B9D.PUMPSWAP_IDL_PATH, B9D.PUMPSWAP_IDL_SHA256)):
            self.database.execute(
                "INSERT INTO program_version VALUES (?,?,?,?,?,?,?,?)",
                (program, B9D.OBSERVATION_RANGE[0], B9D.OBSERVATION_RANGE[1], path,
                 digest, self.SLOT - 1, f"evidence:{program}", "covered"))
        self.saved_verify = B9D.verify_artifact
        self.verify_calls = 0

        def verified(*args, **kwargs):
            self.verify_calls += 1
            return {"integrity": "ok"}

        B9D.verify_artifact = verified
        self.addCleanup(lambda: setattr(B9D, "verify_artifact", self.saved_verify))

    def add_body(self, signature, transaction_index, instructions, meta=None):
        keys = [B9D.base58_decode(B9D.PUMP_PROGRAM), bytes(range(32))]
        result = as_result(build_transaction(keys, instructions), meta=meta, slot=self.SLOT)
        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
        self.database.execute(
            "INSERT INTO transaction_coordinate VALUES (?,?,?)",
            (signature, self.SLOT, transaction_index))
        B9D.store_raw(self.database, "raw_transaction", "signature", signature,
                      "getTransaction", [signature], raw, received_at=1)

    def known(self, name="buy"):
        """A REAL discriminator from the pinned Pump IDL, plus its name.

        Fabricated maps are no longer accepted: the classifier is derived from the revision the
        artifact's own program_version rows declare, so a test map that is not that revision is
        refused. Using a real instruction keeps the test honest about what it exercises.
        """
        idl = json.loads((ROOT / B9D.PUMP_IDL_PATH).read_bytes())
        entry = next(i for i in idl["instructions"] if i["name"] == name)
        return bytes(entry["discriminator"]), name

    def test_materializes_outer_and_inner_coordinates_and_records_unknown_target(self):
        known, known_name = self.known()
        unknown = b"unknown!"
        meta = {"innerInstructions": [{"index": 0, "instructions": [{
            "programIdIndex": 0, "accounts": [1], "data": B9D.base58(unknown)}]}]}
        self.add_body("sig", 3, [(0, [1], known)], meta)
        summary = B9D.decode_artifact(self.database, check_sources=False)
        self.assertEqual(self.verify_calls, 1, "publication verification is a precondition")
        self.assertEqual(summary["instructions"], 2)
        self.assertEqual(summary["target_instructions"], 2)
        self.assertEqual(summary["classification_failures"], 1)
        rows = self.database.execute(
            "SELECT outer_index,inner_index,idl_name,discriminator FROM instruction "
            "ORDER BY slot,transaction_index,outer_index,inner_index").fetchall()
        self.assertEqual(rows, [(0, -1, known_name, known.hex()),
                                (0, 0, None, unknown.hex())])
        failure = self.database.execute(
            "SELECT signature,outer_index,inner_index,reason FROM classification_failure").fetchone()
        self.assertEqual(failure[:3], ("sig", 0, 0))
        self.assertIn("unknown", failure[3])

    def test_existing_derived_rows_are_never_mixed_or_overwritten(self):
        self.database.execute(
            "INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (self.SLOT, 0, 0, -1, "old", "program", None, None, 0, "[]", 0))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.decode_artifact(self.database, check_sources=False)
        self.assertIn("refusing to mix or overwrite", str(ctx.exception))

    def test_intervals_declaring_two_revisions_cannot_build_one_map(self):
        """Defence in depth, unreachable via decode_artifact because program_version_rows already
        binds every interval to the single pin. Tested directly so the guard is not merely present.
        """
        low, high = B9D.OBSERVATION_RANGE
        rows = [{"program_id": B9D.PUMP_PROGRAM, "from_slot": low, "to_slot": low + 10,
                 "idl_path": B9D.PUMP_IDL_PATH, "idl_sha256": B9D.PUMP_IDL_SHA256,
                 "coverage": "covered"},
                {"program_id": B9D.PUMP_PROGRAM, "from_slot": low + 11, "to_slot": high,
                 "idl_path": "research/other.json", "idl_sha256": "b" * 64,
                 "coverage": "covered"}]
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.interval_idl_maps({B9D.PUMP_PROGRAM: rows})
        self.assertIn("distinct revisions", str(ctx.exception))

    def test_a_fabricated_decoder_map_is_refused(self):
        """Reproduced defect: the intervals were validated against the module pins while
        classification used a separately supplied map. A fabricated map produced a row labelled
        `totally_invented_instruction`, zero classification failures, and metadata still naming the
        pinned revision — asserted and used were different objects."""
        fake = bytes(range(200, 208))
        self.add_body("sig", 0, [(0, [], fake)])
        fabricated = {B9D.PUMP_PROGRAM: {fake.hex(): "totally_invented_instruction"},
                      B9D.PUMPSWAP_PROGRAM: {}}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.decode_artifact(self.database, check_sources=False, idl_maps=fabricated)
        self.assertIn("unattributable", str(ctx.exception))
        self.assertEqual(self.database.execute(
            "SELECT count(*) FROM instruction").fetchone()[0], 0)

    def test_the_map_is_derived_from_the_declared_revision(self):
        """The boundary: an unknown target discriminator must still be recorded, not refused."""
        fake = bytes(range(200, 208))
        self.add_body("sig", 0, [(0, [], fake)])
        summary = B9D.decode_artifact(self.database, check_sources=False)
        self.assertEqual(summary["classification_failures"], 1)
        self.assertEqual(self.database.execute(
            "SELECT idl_name,target FROM instruction").fetchone(), (None, 1))

    def test_an_unnamed_unaccounted_target_row_rolls_the_whole_pass_back(self):
        """If classify_instruction ever stops returning a reason, the rows must not commit."""
        known, _ = self.known()
        self.add_body("sig", 0, [(0, [], bytes(range(200, 208)))])
        saved = B9D.classify_instruction
        B9D.classify_instruction = lambda program, data, maps: (True, None, "aa", None)
        self.addCleanup(lambda: setattr(B9D, "classify_instruction", saved))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.decode_artifact(self.database, check_sources=False)
        self.assertIn("neither named nor recorded", str(ctx.exception))
        self.assertEqual(self.database.execute(
            "SELECT count(*) FROM instruction").fetchone()[0], 0,
            "the accounting assertion runs inside the transaction, so nothing commits")

    def test_boundary_coverage_is_checked_before_any_derived_write(self):
        self.database.execute(
            "DELETE FROM program_version WHERE program_id=?", (B9D.PUMPSWAP_PROGRAM,))
        self.add_body("sig", 0, [(0, [], self.known()[0])])
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.decode_artifact(self.database, check_sources=False)
        self.assertIn("no boundary evidence covers", str(ctx.exception))
        self.assertEqual(self.database.execute(
            "SELECT count(*) FROM instruction").fetchone()[0], 0)

    def test_a_covered_but_different_revision_is_not_decoded_with_the_current_map(self):
        self.database.execute(
            "UPDATE program_version SET idl_sha256=? WHERE program_id=?",
            ("0" * 64, B9D.PUMP_PROGRAM))
        self.add_body("sig", 0, [(0, [], self.known()[0])])
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.decode_artifact(self.database, check_sources=False)
        self.assertIn("different revision", str(ctx.exception))
        self.assertEqual(self.database.execute(
            "SELECT count(*) FROM instruction").fetchone()[0], 0)


class PublicationGateTests(unittest.TestCase):
    """§11 gates PUBLICATION, where the collection seams gate collection.

    Built on a tiny complete artifact: the population constants are patched down so a two-signature
    fixture counts as exact, which keeps the gates themselves under test rather than the numbers.
    """

    SLOT_A, SLOT_B = 700, 701

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.path = self.dir / "b9d.sqlite"
        saved = (B9D.EXPECTED_SLOTS, B9D.EXPECTED_SIGNATURES)
        B9D.EXPECTED_SLOTS, B9D.EXPECTED_SIGNATURES = 2, 2
        self.addCleanup(lambda: setattr(B9D, "EXPECTED_SLOTS", saved[0]))
        self.addCleanup(lambda: setattr(B9D, "EXPECTED_SIGNATURES", saved[1]))
        self.build()

    def block_body(self, signatures):
        return json.dumps({"jsonrpc": "2.0", "id": 1,
                           "result": {"signatures": signatures}}).encode()

    def transaction_body(self, slot):
        return json.dumps({"jsonrpc": "2.0", "id": 1,
                           "result": {"slot": slot, "meta": {"err": None}}}).encode()

    def store(self, database, table, key_column, key, raw):
        database.execute(
            f"INSERT INTO {table} ({key_column},method,params_json,received_at_unix,"
            "response_sha256,raw_zlib) VALUES (?,?,?,?,?,?)",
            (key, "m", "[]", 0.0, hashlib.sha256(raw).hexdigest(), zlib.compress(raw, 6)))

    def build(self):
        database = B9D.connect(str(self.path))
        B9D.schema(database)
        with database:
            # sigA is second in its block, so a replay that ignored position would still pass a
            # count check but fail here.
            self.store(database, "raw_block_signatures", "slot", self.SLOT_A,
                       self.block_body(["other", "sigA"]))
            self.store(database, "raw_block_signatures", "slot", self.SLOT_B,
                       self.block_body(["sigB"]))
            database.execute("INSERT INTO transaction_coordinate VALUES ('sigA',?,1)", (self.SLOT_A,))
            database.execute("INSERT INTO transaction_coordinate VALUES ('sigB',?,0)", (self.SLOT_B,))
            self.store(database, "raw_transaction", "signature", "sigA",
                       self.transaction_body(self.SLOT_A))
            self.store(database, "raw_transaction", "signature", "sigB",
                       self.transaction_body(self.SLOT_B))
            database.execute("INSERT INTO metadata VALUES ('b9c_sha256',?)", (B9D.B9C_SHA256,))
            database.execute("INSERT INTO metadata VALUES ('b9a_sha256',?)", (B9D.B9A_SHA256,))
        database.close()

    def open(self):
        database = B9D.connect(str(self.path))
        self.addCleanup(database.close)
        return database

    def test_a_complete_consistent_artifact_passes_every_gate(self):
        summary = B9D.verify_artifact(self.open(), check_sources=False)
        self.assertEqual(summary["integrity"], "ok")
        self.assertEqual(summary["raw_hashes"]["raw_transaction"], 2)
        self.assertEqual(summary["raw_hashes"]["raw_block_signatures"], 2)
        self.assertEqual(summary["coordinates_replayed"], 2)
        self.assertEqual(summary["body_slots_reconciled"], 2)

    def test_a_tampered_response_body_fails_its_hash(self):
        database = self.open()
        with database:
            database.execute("UPDATE raw_transaction SET raw_zlib=? WHERE signature='sigA'",
                             (zlib.compress(b'{"result":{"slot":700}}', 6),))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_raw_hashes(database)
        self.assertIn("recorded", str(ctx.exception))

    def test_bytes_that_do_not_decompress_fail_visibly(self):
        database = self.open()
        with database:
            database.execute("UPDATE raw_transaction SET raw_zlib=? WHERE signature='sigA'",
                             (b"not zlib at all",))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_raw_hashes(database)
        self.assertIn("do not decompress", str(ctx.exception))

    def test_a_wrong_transaction_index_is_caught_by_replay_not_by_counting(self):
        """The gate that matters: the index is derived, and every reserve path is ordered by it."""
        database = self.open()
        with database:
            database.execute(
                "UPDATE transaction_coordinate SET transaction_index=0 WHERE signature='sigA'")
        self.assertEqual(  # the count is still exactly right, so no population seam fires
            database.execute("SELECT count(*) FROM transaction_coordinate").fetchone()[0], 2)
        B9D.assert_coordinate_population(database)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.replay_coordinates_from_raw(database)
        self.assertIn("places it at 1", str(ctx.exception))

    def test_a_coordinate_with_no_preserved_block_body_fails(self):
        database = self.open()
        with database:
            database.execute("DELETE FROM raw_block_signatures WHERE slot=?", (self.SLOT_A,))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.replay_coordinates_from_raw(database)
        self.assertIn("no preserved block body", str(ctx.exception))

    def test_a_block_response_without_a_signature_list_fails(self):
        database = self.open()
        raw = json.dumps({"result": {"blockhash": "x"}}).encode()
        with database:
            database.execute(
                "UPDATE raw_block_signatures SET raw_zlib=?, response_sha256=? WHERE slot=?",
                (zlib.compress(raw, 6), hashlib.sha256(raw).hexdigest(), self.SLOT_A))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.replay_coordinates_from_raw(database)
        self.assertIn("no `signatures` list", str(ctx.exception))

    def test_a_body_reporting_a_different_slot_is_refused(self):
        database = self.open()
        raw = self.transaction_body(self.SLOT_A + 999)
        with database:
            database.execute(
                "UPDATE raw_transaction SET raw_zlib=?, response_sha256=? WHERE signature='sigA'",
                (zlib.compress(raw, 6), hashlib.sha256(raw).hexdigest()))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_body_slots(database)
        self.assertIn("disagreeing", str(ctx.exception))

    def test_an_incomplete_artifact_cannot_reach_the_evidence_gates(self):
        database = self.open()
        with database:
            database.execute("DELETE FROM raw_transaction WHERE signature='sigB'")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_artifact(database, check_sources=False)
        self.assertIn("raw body phase is incomplete", str(ctx.exception))

    def test_a_changed_source_artifact_is_refused(self):
        database = self.open()
        with database:
            database.execute("UPDATE metadata SET value='deadbeef' WHERE key='b9c_sha256'")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_source_artifacts(database)
        self.assertIn("changed after the run", str(ctx.exception))

    def test_an_artifact_recording_no_sources_cannot_prove_its_provenance(self):
        database = self.open()
        with database:
            database.execute("DELETE FROM metadata WHERE key LIKE '%_sha256'")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_source_artifacts(database)
        self.assertIn("which evidence it was built from", str(ctx.exception))

    def test_same_size_but_different_signature_sets_is_refused(self):
        """Reproduced defect: both seams count rows, so two tables of equal size over DIFFERENT
        sets passed every gate. `verify_body_slots` reconciled only the intersection and returned a
        smaller number nothing compared, and `decode_artifact` then decoded that intersection,
        reported success and wrote `decoded_at_unix`."""
        database = self.open()
        with database:
            # Replace one body with an orphan: still exactly 2 bodies and 2 coordinates.
            database.execute("DELETE FROM raw_transaction WHERE signature='sigB'")
            self.store(database, "raw_transaction", "signature", "sigOrphan",
                       self.transaction_body(999))
        self.assertEqual(  # sizes still match, which is why counting was not enough
            database.execute("SELECT count(*) FROM raw_transaction").fetchone()[0],
            database.execute("SELECT count(*) FROM transaction_coordinate").fetchone()[0])
        B9D.assert_raw_transaction_population(database)
        B9D.assert_coordinate_population(database)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_body_population_matches(database)
        message = str(ctx.exception)
        self.assertIn("same size but not the same set", message)
        self.assertIn("1 coordinate(s) have no preserved body", message)
        self.assertIn("1 preserved body(ies) have no coordinate", message)
        with self.assertRaises(B9D.FreezeViolation):
            B9D.verify_artifact(database, check_sources=False)

    def test_a_missing_body_alone_is_refused(self):
        """Separated from the orphan case: my first regression test had both at once, so either
        half of `if missing or orphan` alone still fired and a mutation proved it."""
        database = self.open()
        with database:
            database.execute("DELETE FROM raw_transaction WHERE signature='sigB'")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_body_population_matches(database)
        self.assertIn("1 coordinate(s) have no preserved body", str(ctx.exception))

    def test_an_orphan_body_alone_is_refused(self):
        database = self.open()
        with database:
            database.execute("DELETE FROM transaction_coordinate WHERE signature='sigB'")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.assert_body_population_matches(database)
        self.assertIn("1 preserved body(ies) have no coordinate", str(ctx.exception))

    def test_a_short_reconciliation_count_is_asserted_not_merely_returned(self):
        """The number was already computed; nothing compared it to the population."""
        database = self.open()
        saved = B9D.verify_body_slots
        B9D.verify_body_slots = lambda db: B9D.EXPECTED_SIGNATURES - 1
        self.addCleanup(lambda: setattr(B9D, "verify_body_slots", saved))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_artifact(database, check_sources=False)
        self.assertIn("bodies reconciled against their coordinates", str(ctx.exception))

    def test_a_failing_integrity_check_is_refused(self):
        """A corrupt page store cannot be produced reliably in a test, so the gate is driven
        directly. Without this, deleting the check changed nothing observable."""
        class Cursor:
            def fetchone(self):
                return ("*** in database main *** wrong # of entries in index",)

        class Corrupt:
            def execute(self, sql):
                return Cursor()

        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9D.verify_integrity(Corrupt())
        self.assertIn("integrity_check", str(ctx.exception))
        self.assertEqual(B9D.verify_integrity(self.open()), "ok")

    def test_the_cli_opens_the_artifact_read_only(self):
        """Publication verification must not be able to repair the evidence it checks."""
        opened = []
        saved = B9D.connect
        B9D.connect = lambda path, readonly=False: opened.append(readonly) or saved(path, readonly)
        self.addCleanup(lambda: setattr(B9D, "connect", saved))
        B9D.main(["verify-artifact", str(self.path), "--skip-sources"])
        self.assertEqual(opened, [True])


class CoordinateSeamWiringTests(unittest.TestCase):
    """The seam guard is only worth anything if the production call site actually passes it.

    `assert_coordinate_population` and `transaction_body_coordinates` were already covered, but
    nothing asserted that `collect_raw_population` requests the check on an unbounded run. Mutating
    its argument to `require_complete=False` left the whole suite green while un-gating production —
    the guard was tested and its wiring was not. These tests exercise the real function.

    Hermetic: source hashing and the frozen-population read are stubbed, every block is already
    preserved so the block loop issues nothing, and `max_transactions=0` stops the body loop before
    its first request. `rpc_request` is replaced with a raiser, so any network attempt fails loudly.
    """

    SLOTS = (500, 501)

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.path = self.dir / "b9d.sqlite"
        self.requested = []

        grouped = {slot: [f"sig{slot}"] for slot in self.SLOTS}
        saved = (B9D.assert_sources, B9D.frozen_population_by_slot, B9D.rpc_request)

        def refuse(*args, **kwargs):
            self.requested.append(args)
            raise AssertionError("a network request was attempted; the test is not hermetic")

        B9D.assert_sources = lambda *a, **k: {}
        B9D.frozen_population_by_slot = lambda *a, **k: grouped
        B9D.rpc_request = refuse
        self.addCleanup(lambda: setattr(B9D, "assert_sources", saved[0]))
        self.addCleanup(lambda: setattr(B9D, "frozen_population_by_slot", saved[1]))
        self.addCleanup(lambda: setattr(B9D, "rpc_request", saved[2]))

        # Every slot already preserved, with one coordinate each: a deliberately short population.
        database = B9D.connect(str(self.path))
        B9D.schema(database)
        with database:
            for slot in self.SLOTS:
                database.execute(
                    "INSERT INTO raw_block_signatures VALUES (?,?,?,?,?,?)",
                    (slot, "getBlock", "[]", 0.0, "h" * 64, b"\x00"))
                database.execute("INSERT INTO transaction_coordinate VALUES (?,?,?)",
                                 (f"sig{slot}", slot, 0))
        database.close()

    def collect(self, **kwargs):
        max_transactions = kwargs.pop("max_transactions", 0)
        return B9D.collect_raw_population(
            "https://unused.invalid", str(self.path), max_transactions=max_transactions,
            progress_every=0, **kwargs)

    def test_an_unbounded_run_refuses_to_start_bodies_on_a_short_population(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.collect(max_slots=None)
        self.assertIn("coordinate phase is incomplete", str(ctx.exception))
        self.assertEqual(self.requested, [], "it must refuse before any network call")

    def test_a_bounded_probe_deliberately_bypasses_the_completeness_gate(self):
        """The boundary that keeps the guard honest: probes must stay resumable.

        Without this, the fix could degrade into a gate that blocks the bounded probes the
        preregistration relies on for shape verification.
        """
        summary = self.collect(max_slots=1)
        self.assertEqual(summary["transactions_added"], 0)
        self.assertEqual(self.requested, [])

    def test_an_unbounded_return_refuses_a_short_raw_body_population(self):
        """Pin the raw-body guard's production call site, not only its helper.

        The coordinate gate is replaced with an empty, already-complete iterable to isolate the
        next seam. With no bodies to fetch, an unbounded collector reaches the return boundary and
        must still reject the short raw table without making a network request.
        """
        saved = B9D.transaction_body_coordinates
        B9D.transaction_body_coordinates = lambda database, require_complete=True: []
        self.addCleanup(lambda: setattr(B9D, "transaction_body_coordinates", saved))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.collect(max_slots=None, max_transactions=None)
        self.assertIn("raw body phase is incomplete", str(ctx.exception))
        self.assertEqual(self.requested, [], "it must refuse without any network call")

    def test_a_bounded_body_probe_deliberately_bypasses_the_raw_completion_gate(self):
        """The reverse mutation: partial body probes must remain resumable."""
        summary = self.collect(max_slots=1, max_transactions=0)
        self.assertEqual(summary["transactions_added"], 0)
        self.assertEqual(self.requested, [])


class ExecutionGateTests(unittest.TestCase):
    """§10: authorized collection stays credential-redacting and fail-closed."""

    def test_run_still_requires_an_endpoint_environment_variable(self):
        saved = os.environ.pop("B9D_TEST_RPC", None)
        try:
            with self.assertRaises(SystemExit) as ctx:
                B9D.main(["run", "x.sqlite", "--rpc-env", "B9D_TEST_RPC"])
            self.assertIn("missing RPC endpoint", str(ctx.exception))
        finally:
            if saved is not None:
                os.environ["B9D_TEST_RPC"] = saved

    def test_endpoint_reference_strips_query_credentials(self):
        self.assertEqual(B9D.endpoint_reference(
            "https://mainnet.example/rpc?api-key=secret"), "https://mainnet.example/rpc")

    def test_transaction_preflight_requires_every_frozen_meta_field(self):
        meta = {field: [] for field in B9D.REQUIRED_META_FIELDS}
        meta.update({"err": None, "fee": 1})
        result = {"meta": meta, "transaction": ["AAAA", "base64"]}
        self.assertTrue(B9D.assert_transaction_shape("sig", result))
        del meta["fee"]
        with self.assertRaises(B9D.FreezeViolation):
            B9D.assert_transaction_shape("sig", result)

    def test_raw_response_resume_requires_identical_bytes(self):
        database = sqlite3.connect(":memory:")
        B9D.schema(database)
        self.assertTrue(B9D.store_raw(database, "raw_transaction", "signature", "s",
                                      "getTransaction", ["s"], b"one", received_at=1))
        self.assertFalse(B9D.store_raw(database, "raw_transaction", "signature", "s",
                                       "getTransaction", ["s"], b"one", received_at=2))
        with self.assertRaises(B9D.FreezeViolation):
            B9D.store_raw(database, "raw_transaction", "signature", "s",
                          "getTransaction", ["s"], b"two", received_at=3)

    def test_verify_is_offline_and_init_creates_an_artifact(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(B9D.main(["init", str(directory / "a.sqlite")]), 0)
        database = sqlite3.connect(directory / "a.sqlite")
        names = {row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        database.close()
        self.assertIn("raw_block_signatures", names)
        self.assertEqual(metadata["pump_idl_sha256"], B9D.PUMP_IDL_SHA256)
        # Both target interfaces are now pinned into the artifact, with provenance. An artifact
        # that cannot say which interface revision decoded it is not auditable.
        self.assertEqual(metadata["pumpswap_idl_sha256"], B9D.PUMPSWAP_IDL_SHA256)
        self.assertEqual(metadata["idl_source_commit"], B9D.IDL_SOURCE_COMMIT)
        self.assertNotIn("pumpswap_idl_status", metadata)


if __name__ == "__main__":
    unittest.main()
