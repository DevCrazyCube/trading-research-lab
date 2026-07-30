"""Offline tests for the B9d scaffold.

Every test here runs with no network and no dependency on the 840 MiB B9c artifact: the population
logic is exercised against small synthetic databases built to the same schema. The real artifact is
asserted at run time by `verify`, which is where a mismatch must stop a run — a unit test that
streams 1.35M rows would move that check into the suite and slow it into disuse.
"""
import hashlib
import importlib.util
import json
import os
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

    def test_two_instructions_cannot_share_a_canonical_key(self):
        database = self.artifact()
        row = (5, 0, 1, -1, "sig", B9D.PUMP_PROGRAM, "aa", "buy", 1, "[]", 24)
        database.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        with self.assertRaises(sqlite3.IntegrityError):
            database.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        database.close()


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
        return B9D.collect_raw_population(
            "https://unused.invalid", str(self.path), max_transactions=0,
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
