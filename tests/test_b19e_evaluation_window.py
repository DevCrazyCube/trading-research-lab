"""Tests for the evaluation window adapter. No network.

The adapter is the one place where a study meets real data, so it is where a study can be
invalidated without any study changing: by feeding it development data, by feeding it a shape the
study reads as absence, by quietly rebasing its denominator, or by running it twice and keeping the
better pass. Each of those is asserted against here.
"""
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load("b19e", "b19e_evaluation_window.py")
B19D = _load("b19d_for_window", "b19d_non_issuance_signal.py")


class TheStudiesStayBlind(unittest.TestCase):
    """The property the whole separation exists to protect, asserted from the outside."""

    def test_no_study_module_names_the_window(self):
        for module in ("b19b_exit_timing_policy", "b19c_capacity_wall",
                       "b19d_non_issuance_signal"):
            with self.subTest(module=module):
                source = (ROOT / "scripts" / f"{module}.py").read_text()
                self.assertNotIn("b11a", source,
                                 "wiring the window into a study destroys the blindness that "
                                 "makes its result worth reporting")

    def test_the_adapter_computes_no_outcome_of_its_own(self):
        """Every figure must come from the study. The adapter transports and counts, nothing more.

        Checked by absence of the arithmetic a result is made of: no median, no order statistic,
        no threshold comparison against zero. If the adapter grew one, a reader could no longer
        tell which document a number came from.
        """
        source = (ROOT / "scripts" / "b19e_evaluation_window.py").read_text()
        for forbidden in ("def exact_median", "def order_statistic", "survives_costs ="):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class FreshnessIsEvidenceNotAFilename(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b19e-"))
        self.paths = self.directory / "paths.sqlite"
        connection = sqlite3.connect(self.paths)
        connection.execute("CREATE TABLE observation (bonding_curve TEXT, slot INTEGER)")
        connection.commit()
        connection.close()

    def _observations(self, slots):
        connection = sqlite3.connect(self.paths)
        connection.executemany("INSERT INTO observation VALUES ('c', ?)", [(s,) for s in slots])
        connection.commit()
        connection.close()

    def test_a_window_overlapping_the_burned_range_is_refused(self):
        self._observations([433_900_000, 435_600_000])
        with self.assertRaisesRegex(B.WindowRefused, "burned range"):
            B.assert_fresh(self.paths)

    def test_a_window_clear_of_the_burned_range_is_accepted(self):
        self._observations([435_600_000, 437_000_000])
        got = B.assert_fresh(self.paths)
        self.assertEqual(got["overlap_observations"], 0)
        self.assertEqual(got["window_min_slot"], 435_600_000)

    def test_an_empty_window_is_refused_rather_than_reported_as_clean(self):
        """Zero overlapping observations is also what an empty file reports."""
        with self.assertRaisesRegex(B.WindowRefused, "no observations"):
            B.assert_fresh(self.paths)


class TheDenominatorIsStatedInFull(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b19e-census-"))
        self.subsample = self.directory / "subsample.sqlite"
        self.paths = self.directory / "paths.sqlite"

    def _build(self, cohort, with_path):
        connection = sqlite3.connect(self.subsample)
        connection.execute("CREATE TABLE cohort_identity (bonding_curve TEXT, is_mayhem_mode INT)")
        connection.executemany("INSERT INTO cohort_identity VALUES (?,?)", cohort)
        connection.commit()
        connection.close()
        connection = sqlite3.connect(self.paths)
        connection.execute("CREATE TABLE curve (bonding_curve TEXT)")
        connection.executemany("INSERT INTO curve VALUES (?)", [(c,) for c in with_path])
        connection.commit()
        connection.close()

    def test_the_three_numbers_are_reported_and_add_up(self):
        self._build([("a", 0), ("b", 0), ("m", 1)], ["a", "b"])
        census = B.cohort_census(self.subsample, self.paths)
        self.assertEqual(census["subsampled"], 3)
        self.assertEqual(census["excluded_out_of_regime_mayhem"], 1)
        self.assertEqual(census["evaluable"], 2)

    def test_an_in_regime_curve_without_a_path_is_collection_loss_and_refuses(self):
        """The check that would have caught real data loss, rather than shrinking the denominator.

        Silently reporting `evaluable: 1` here would present collection loss as a smaller cohort.
        """
        self._build([("a", 0), ("b", 0)], ["a"])
        with self.assertRaisesRegex(B.WindowRefused, "collection loss"):
            B.cohort_census(self.subsample, self.paths)

    def test_a_mayhem_curve_carrying_a_path_refuses(self):
        self._build([("m", 1)], ["m"])
        with self.assertRaisesRegex(B.WindowRefused, "out of regime"):
            B.cohort_census(self.subsample, self.paths)


class TheFlattenedBlockIsWhatTheStudyDeclares(unittest.TestCase):
    RECORD = {
        "coordinate": {"slot": 437_000_000, "transaction_index": 3,
                       "outer_index": 0, "inner_index": -1},
        "features": {"creator_initial_buy_present": True, "t0_is_launch_instruction": False,
                     "is_cashback_enabled": True},
        "grouping": {"bonding_curve": "CURVE", "creator": "C", "create_user": "C"},
    }

    def test_the_flattened_block_actually_fires_the_studys_signals(self):
        """The regression: the nested record made every t0 signal return None for every curve.

        Asserted by running b19d's own signal_coordinate over the adapter's output rather than by
        comparing keys, because the defect was that a wrong shape produced no error at all.
        """
        features = B.flatten_features([self.RECORD])
        fired = {}
        for signal in B19D.SIGNALS:
            if signal["kind"] != "t0_boolean":
                continue
            fired[signal["signal_id"]] = B19D.signal_coordinate(signal, "CURVE", features, {})
        self.assertEqual(fired["S1_CREATOR_INITIAL_BUY_PRESENT"], 437_000_000)
        self.assertEqual(fired["S4_CASHBACK_ENABLED"], 437_000_000)
        # S3 expects True and the record says False: a genuine did-not-fire, not an absence.
        self.assertIsNone(fired["S3_T0_IS_LAUNCH_INSTRUCTION"])
        # S2 is S1's complement over the same field and must also be a real negative.
        self.assertIsNone(fired["S2_NO_CREATOR_INITIAL_BUY"])

    def test_the_baseline_reads_the_same_block(self):
        features = B.flatten_features([self.RECORD])
        self.assertEqual(B19D.baseline_coordinate("baseline_launch", "CURVE", features, {}),
                         437_000_000)

    def test_two_records_for_one_curve_are_refused(self):
        with self.assertRaisesRegex(B.WindowRefused, "two feature records"):
            B.flatten_features([self.RECORD, self.RECORD])

    def test_the_raw_nested_record_is_refused_by_the_study(self):
        """Proof the guard is load-bearing: without flattening, b19d now refuses instead of None."""
        with self.assertRaises(B19D.CorpusContractViolation):
            B19D.signal_coordinate(B19D.SIGNALS[0], "CURVE", {"CURVE": self.RECORD}, {})


class OnePassPerStudy(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b19e-ledger-"))
        self.ledger = self.directory / "ledger.json"

    def test_a_second_pass_is_refused(self):
        B.record_pass("STUDY_V1", "w" * 64, "r" * 64, path=self.ledger)
        with self.assertRaisesRegex(B.WindowRefused, "already read"):
            B.assert_unused("STUDY_V1", path=self.ledger)

    def test_a_different_study_is_unaffected(self):
        B.record_pass("STUDY_V1", "w" * 64, "r" * 64, path=self.ledger)
        ledger, prior = B.assert_unused("OTHER_V1", path=self.ledger)
        self.assertEqual(prior, [])

    def test_superseding_requires_a_reason_and_keeps_both_entries(self):
        """Nothing is ever deleted. A discarded first pass is the thing worth seeing."""
        B.record_pass("STUDY_V1", "w" * 64, "r" * 64, path=self.ledger)
        second = B.record_pass("STUDY_V1", "x" * 64, "s" * 64, path=self.ledger,
                               supersede_reason="the first pass used a mis-shaped corpus")
        entries = json.loads(self.ledger.read_bytes())["entries"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(second["supersedes"], [1])
        self.assertEqual(entries[0]["result_sha256"], "r" * 64,
                         "the superseded entry keeps its own result hash")

    def test_the_ledger_records_which_window_was_read(self):
        entry = B.record_pass("STUDY_V1", "w" * 64, "r" * 64, path=self.ledger)
        self.assertEqual(entry["window_sha256"], "w" * 64)


class TheWindowDigestDescribesContentNotBytes(unittest.TestCase):
    def _window(self, real_quote):
        return {
            "paths": {"c": [{"slot": 1, "transaction_index": 0, "outer_index": 0,
                             "inner_index": -1, "virtual_quote": 30, "virtual_token": 1000,
                             "real_quote": real_quote, "real_token": 900, "quote_mint": "So111",
                             "mayhem_mode": False, "complete": False}]},
            "features": {"c": {"t0_slot": 1, "is_cashback_enabled": True}},
        }

    def test_the_same_content_digests_the_same(self):
        self.assertEqual(B.window_digest(self._window(5)), B.window_digest(self._window(5)))

    def test_different_content_digests_differently(self):
        self.assertNotEqual(B.window_digest(self._window(5)), B.window_digest(self._window(6)))

    def test_a_float_reaching_the_digest_is_refused(self):
        with self.assertRaisesRegex(B.WindowRefused, "float"):
            B.window_digest(self._window(5.0))


if __name__ == "__main__":
    unittest.main()
