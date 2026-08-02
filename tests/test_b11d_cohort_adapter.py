"""Tests for the B11d fresh-cohort adapter.

Synthetic B7d databases only. Nothing here touches a network, and the B9c/B9d compatibility is
demonstrated by running their actual SQL against the artifact rather than asserting it.
"""
import importlib.util
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = _load("b11d_cohort_adapter", "b11d_cohort_adapter.py")
B9D = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")

B7D_SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE slot_scan (slot INTEGER PRIMARY KEY, status TEXT NOT NULL, blockhash TEXT,
  previous_blockhash TEXT, parent_slot INTEGER, block_time INTEGER, transaction_count INTEGER,
  pump_transaction_count INTEGER, create_instruction_count INTEGER, error TEXT,
  scanned_at_unix REAL NOT NULL);
CREATE TABLE create_event (slot INTEGER NOT NULL, transaction_index INTEGER NOT NULL,
  outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
  signature TEXT NOT NULL, block_time INTEGER, mint TEXT NOT NULL, bonding_curve TEXT NOT NULL,
  creator TEXT, user TEXT, is_mayhem_mode INTEGER, is_cashback_enabled INTEGER, quote_mint TEXT,
  fields_json TEXT NOT NULL, event_payload_base64 TEXT NOT NULL,
  PRIMARY KEY (slot, transaction_index, outer_instruction_index, inner_instruction_index));
CREATE TABLE decode_error (slot INTEGER NOT NULL, transaction_index INTEGER NOT NULL,
  outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
  signature TEXT NOT NULL, error TEXT NOT NULL,
  PRIMARY KEY (slot, transaction_index, outer_instruction_index, inner_instruction_index));
"""

CREATES = ((100, "MintA", "CurveA", 0), (101, "MintB", "CurveB", 1), (104, "MintC", "CurveC", 0))


class AdapterCase(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="b11d-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def make_source(self, start=100, end_exclusive=105, creates=CREATES, statuses=None,
                    decode_errors=0, name="b7d.sqlite"):
        path = self.dir / name
        database = sqlite3.connect(path)
        database.executescript(B7D_SCHEMA)
        database.executemany("INSERT INTO metadata VALUES (?,?)",
                             [("start_slot", str(start)),
                              ("end_slot_exclusive", str(end_exclusive))])
        statuses = statuses or {103: "skipped"}
        for slot in range(start, end_exclusive):
            database.execute("INSERT INTO slot_scan VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (slot, statuses.get(slot, "retrieved"), None, None, None, None,
                              0, 0, 0, None, 0.0))
        for index, (slot, mint, curve, mayhem) in enumerate(creates):
            database.execute(
                "INSERT INTO create_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (slot, 0, 0, index, f"sig{index}", None, mint, curve, "cr", "us", mayhem,
                 0, "So111", "{}", "AA=="))
        for index in range(decode_errors):
            database.execute("INSERT INTO decode_error VALUES (?,?,?,?,?,?)",
                             (start, 9, 9, index, f"bad{index}", "undecodable"))
        database.commit()
        database.close()
        return path

    def build(self, **kwargs):
        source = self.make_source(**kwargs)
        output = self.dir / "cohort.sqlite"
        return source, output, A.build(source, output)


class CompatibilityTests(AdapterCase):
    """Demonstrated by running the consumers' actual SQL, not asserted."""

    def test_b9cs_own_query_returns_the_cohort(self):
        _, output, _ = self.build()
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        rows = database.execute(
            "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint"
        ).fetchall()
        self.assertEqual(rows, [("MintA", "CurveA", 100), ("MintB", "CurveB", 101),
                                ("MintC", "CurveC", 104)])

    def test_b9ds_mayhem_query_returns_the_regime(self):
        _, output, _ = self.build()
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        self.assertEqual(dict(database.execute(
            "SELECT bonding_curve, is_mayhem_mode FROM outcome")),
            {"CurveA": 0, "CurveB": 1, "CurveC": 0})

    def test_b9ds_tradable_identity_query_excludes_mayhem(self):
        _, output, _ = self.build()
        identity = B9D.tradable_cohort_identity(str(output))
        self.assertEqual(identity, {"MintA": "CurveA", "MintC": "CurveC"})

    def test_the_outcome_view_exposes_four_columns_and_no_reserves(self):
        _, output, _ = self.build()
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        columns = [row[1] for row in database.execute("PRAGMA table_info(outcome)")]
        self.assertEqual(tuple(columns), A.COHORT_COLUMNS)
        for banned in ("real_quote_reserves", "virtual_token_reserves", "complete",
                       "account_present", "token_total_supply"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, columns)

    def test_the_real_table_is_not_called_outcome(self):
        """The view exists so the consumers' SQL works; the table underneath is named for what it
        actually holds, so nobody reading the schema believes there are outcomes in it."""
        _, output, _ = self.build()
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        kinds = dict(database.execute("SELECT name,type FROM sqlite_master WHERE name='outcome'"))
        self.assertEqual(kinds, {"outcome": "view"})
        self.assertTrue(database.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cohort_identity'").fetchone())

    def test_the_view_is_a_projection_not_the_table_renamed(self):
        """The table carries create-event provenance the consumers never read. Its absence from
        the view is what proves the view selects columns rather than everything."""
        _, output, _ = self.build()
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        table = [row[1] for row in database.execute("PRAGMA table_info(cohort_identity)")]
        view = [row[1] for row in database.execute("PRAGMA table_info(outcome)")]
        self.assertIn("create_signature", table)
        self.assertNotIn("create_signature", view)
        self.assertEqual(tuple(view), A.COHORT_COLUMNS)

    def test_a_view_exposing_the_whole_table_is_refused(self):
        _, output, _ = self.build()
        database = sqlite3.connect(output)
        database.executescript(
            "DROP VIEW outcome; CREATE VIEW outcome AS SELECT * FROM cohort_identity;")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "exposes outcome columns"):
            A.assert_fresh_cohort(output)


class NoOutcomeTests(AdapterCase):
    """No outcome is manufactured, and the artifact says so."""

    def test_the_artifact_declares_that_it_contains_no_outcome(self):
        _, output, _ = self.build()
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        self.assertEqual(metadata["contains_outcomes"], "0")
        self.assertEqual(metadata["artifact_kind"], "fresh_cohort_identity")

    def test_an_artifact_claiming_outcomes_is_refused(self):
        _, output, _ = self.build()
        database = sqlite3.connect(output)
        database.execute("UPDATE metadata SET value='1' WHERE key='contains_outcomes'")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "claims to contain outcomes"):
            A.assert_fresh_cohort(output)

    def test_an_artifact_that_cannot_say_what_it_is_is_refused(self):
        _, output, _ = self.build()
        database = sqlite3.connect(output)
        database.execute("UPDATE metadata SET value='b9a_outcomes' WHERE key='artifact_kind'")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "may not stand where B9a stood"):
            A.assert_fresh_cohort(output)

    def test_the_burned_b9a_is_not_accepted_as_a_fresh_cohort(self):
        """It has no marker, so it cannot be passed off as one — nor should it be."""
        with self.assertRaises(A.CohortRefused):
            A.assert_fresh_cohort("research/b9a_outcomes.sqlite")


class ExhaustivenessTests(AdapterCase):
    """An unscanned slot is a create nobody looked for."""

    def test_a_gap_in_the_scanned_slots_is_refused(self):
        source = self.make_source()
        database = sqlite3.connect(source)
        database.execute("DELETE FROM slot_scan WHERE slot=102")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "never looked at"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_an_unresolved_slot_is_refused(self):
        for status in A.ERROR_STATUSES:
            with self.subTest(status=status):
                output = self.dir / f"cohort-{status}.sqlite"
                source = self.make_source(statuses={102: status}, name=f"b7d-{status}.sqlite")
                with self.assertRaisesRegex(A.CohortRefused, "nobody could read"):
                    A.build(source, output)

    def test_a_skipped_slot_is_normal(self):
        """A slot the chain never produced is not a gap in the enumeration."""
        _, _, summary = self.build(statuses={101: "skipped", 103: "skipped"})
        self.assertEqual(summary["slots_skipped"], 2)
        self.assertEqual(summary["slots_scanned"], 5)

    def test_a_decode_error_aborts_the_build(self):
        source = self.make_source(decode_errors=2)
        with self.assertRaisesRegex(A.CohortRefused, "lower bound calling itself a population"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_a_create_outside_the_window_is_refused(self):
        """An off-by-one in the enumeration's bounds shows up here rather than downstream."""
        source = self.make_source(creates=CREATES + ((105, "MintD", "CurveD", 0),))
        with self.assertRaisesRegex(A.CohortRefused, "wider than the window"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_the_window_bounds_are_carried_onto_the_artifact(self):
        _, output, summary = self.build(start=100, end_exclusive=105)
        self.assertEqual((summary["start_slot"], summary["end_slot_exclusive"]), (100, 105))
        self.assertEqual(A.assert_fresh_cohort(output)["start_slot"], 100)

    def test_a_source_with_no_window_is_refused(self):
        source = self.make_source()
        database = sqlite3.connect(source)
        database.execute("DELETE FROM metadata WHERE key='end_slot_exclusive'")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "states no end_slot_exclusive"):
            A.build(source, self.dir / "cohort.sqlite")


class IntegrityTests(AdapterCase):
    """Every failure aborts the build; none is dropped, because dropping is filtering."""

    def test_a_missing_identity_is_refused(self):
        source = self.make_source()
        database = sqlite3.connect(source)
        database.execute("UPDATE create_event SET mint='' WHERE bonding_curve='CurveA'")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "not an identity we may guess"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_a_missing_regime_field_is_refused(self):
        source = self.make_source()
        database = sqlite3.connect(source)
        database.execute("UPDATE create_event SET is_mayhem_mode=NULL WHERE bonding_curve='CurveA'")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "an unknown regime is not a permissive one"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_a_curve_created_twice_is_refused(self):
        source = self.make_source(creates=CREATES + ((104, "MintD", "CurveA", 0),))
        with self.assertRaisesRegex(A.CohortRefused, "two create events"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_a_mint_on_two_curves_is_refused(self):
        source = self.make_source(creates=CREATES + ((104, "MintA", "CurveD", 0),))
        with self.assertRaisesRegex(A.CohortRefused, "one-to-one"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_an_empty_cohort_aborts_rather_than_passing_vacuously(self):
        source = self.make_source(creates=())
        with self.assertRaisesRegex(A.CohortRefused, "vacuously"):
            A.build(source, self.dir / "cohort.sqlite")

    def test_nothing_is_filtered_on_an_outcome(self):
        """Every create becomes a member, mayhem included. A cohort selected on any property of
        what happened afterwards would be a cohort selected on the answer."""
        _, output, summary = self.build()
        self.assertEqual(summary["members"], len(CREATES))
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        self.assertEqual(database.execute(
            "SELECT COUNT(*) FROM cohort_identity WHERE is_mayhem_mode=1").fetchone()[0], 1)

    def test_the_adapter_reads_no_outcome_bearing_column(self):
        source = (ROOT / "scripts" / "b11d_cohort_adapter.py").read_text()
        for banned in ("real_quote_reserves", "virtual_token_reserves", "token_total_supply",
                       "account_present", "observed_at_unix"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)


class DeterminismTests(AdapterCase):
    """Same input, same bytes."""

    def test_the_cohort_hash_is_stable_across_builds(self):
        first_source = self.make_source(name="one.sqlite")
        second_source = self.make_source(name="two.sqlite")
        one = A.build(first_source, self.dir / "one-cohort.sqlite")
        two = A.build(second_source, self.dir / "two-cohort.sqlite")
        self.assertEqual(one["cohort_sha256"], two["cohort_sha256"])

    def test_a_changed_member_changes_the_hash(self):
        base = A.build(self.make_source(name="a-source.sqlite"), self.dir / "a-cohort.sqlite")
        other = A.build(
            self.make_source(creates=CREATES[:2] + ((104, "MintZ", "CurveC", 0),),
                             name="b-source.sqlite"),
            self.dir / "b-cohort.sqlite")
        self.assertNotEqual(base["cohort_sha256"], other["cohort_sha256"])

    def test_hash_drift_after_sealing_is_caught(self):
        _, output, _ = self.build()
        database = sqlite3.connect(output)
        database.execute("UPDATE cohort_identity SET launch_slot=999 WHERE mint='MintA'")
        database.commit()
        database.close()
        with self.assertRaisesRegex(A.CohortRefused, "changed after the artifact was sealed"):
            A.assert_fresh_cohort(output)

    def test_an_existing_artifact_is_never_overwritten(self):
        source, output, _ = self.build()
        with self.assertRaisesRegex(A.CohortRefused, "written once"):
            A.build(source, output)

    def test_provenance_records_the_source_and_the_coverage(self):
        source, output, summary = self.build()
        database = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
        self.addCleanup(database.close)
        row = database.execute("SELECT * FROM provenance").fetchone()
        self.assertIn(str(source), row)
        self.assertIn(summary["source_sha256"], row)
        self.assertIn(summary["cohort_sha256"], row)


class B9dSourceModeTests(AdapterCase):
    """b9d must treat a fresh cohort as fresh, and never apply the burned pins to it."""

    def test_a_fresh_cohort_passes_b9ds_source_check(self):
        _, output, _ = self.build()
        inventory = self.dir / "b11a_signatures.sqlite"
        inventory.write_bytes(b"placeholder inventory")
        digests = B9D.assert_sources(str(inventory), str(output))
        self.assertEqual(set(digests), {str(inventory), str(output)})

    def test_a_fresh_pair_is_fresh_mode(self):
        self.assertEqual(B9D.source_mode("x/a.sqlite", "x/b.sqlite"), B9D.SOURCE_MODE_FRESH)

    def test_the_burned_counts_are_not_applied_to_a_fresh_population(self):
        """The pinned counts describe the burned window. Applying them to a fresh one would refuse
        every correct run."""
        self.assertTrue(B9D.assert_population({"sig"}, {1}, mode=B9D.SOURCE_MODE_FRESH))
        with self.assertRaises(B9D.FreezeViolation):
            B9D.assert_population({"sig"}, {1}, mode=B9D.SOURCE_MODE_BURNED)

    def test_an_empty_fresh_population_is_still_refused(self):
        with self.assertRaisesRegex(B9D.FreezeViolation, "collecting nothing"):
            B9D.assert_population(set(), set(), mode=B9D.SOURCE_MODE_FRESH)


if __name__ == "__main__":
    unittest.main()
