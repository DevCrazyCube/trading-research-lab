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


class TheBurnedBoundIsDerivedNotRestated(unittest.TestCase):
    """A window can be fresh by the declared constant and still overlap the burned data.

    B16A.BURNED_RANGE describes the window the burned CREATES were drawn from
    (433,894,233-434,097,833). The burned OBSERVATIONS reach 435,536,000, because a curve keeps
    trading long after it launches. A freshness check against the create window alone accepts
    1.4 million slots of data the studies were developed against -- and passes, rather than fails,
    for the wrong reason.
    """

    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b19e-burned-"))
        self.burned = self.directory / "burned.sqlite"
        self.window = self.directory / "window.sqlite"

    def _corpus(self, path, slots):
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE observation (bonding_curve TEXT, slot INTEGER)")
        connection.executemany("INSERT INTO observation VALUES ('c', ?)", [(s,) for s in slots])
        connection.commit()
        connection.close()

    def test_the_extent_is_wider_than_the_declared_create_window(self):
        self._corpus(self.burned, [433_894_233, 435_536_000])
        extent = B.burned_extent(self.burned)
        self.assertEqual(extent["high"], 435_536_000)
        self.assertGreater(extent["high"], B.B16A.BURNED_RANGE[1],
                           "the observed extent must exceed the declared create window")
        self.assertEqual(extent["source"], "derived_from_the_burned_corpus")

    def test_a_window_the_declared_constant_would_accept_is_refused(self):
        """The regression: slot 435,000,000 is outside the create window and inside the data."""
        self._corpus(self.burned, [433_894_233, 435_536_000])
        self._corpus(self.window, [435_000_000, 435_600_000])
        self.assertGreater(435_000_000, B.B16A.BURNED_RANGE[1],
                           "the fixture must be outside the declared window, or it proves nothing")
        with self.assertRaisesRegex(B.WindowRefused, "burned range"):
            B.assert_fresh(self.window, burned=(B.burned_extent(self.burned)["low"],
                                                B.burned_extent(self.burned)["high"]))

    def test_an_absent_burned_corpus_announces_the_weaker_bound(self):
        """A check that silently weakened itself is worse than no check."""
        extent = B.burned_extent(self.directory / "does-not-exist.sqlite")
        self.assertEqual(extent["source"], "declared_constant_only")
        self.assertIn("narrower than the data", extent["warning"])

    def test_the_real_window_is_clear_of_the_derived_bound(self):
        """Not a fixture: the actual collected window against the actual burned corpus."""
        if not B.PATHS.exists() or not B.BURNED_PATHS.exists():
            self.skipTest("the window or the burned corpus is not present")
        freshness = B.assert_fresh()
        self.assertEqual(freshness["overlap_observations"], 0)
        self.assertGreater(freshness["clear_of_burned_by_slots"], 0,
                           "the window must start after the burned data ENDS, not after the "
                           "burned create window ends")


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


class TheInvariantsAreEnforcedNotEyeballed(unittest.TestCase):
    """Both guards run on the live pass, so neither depends on someone checking the rehearsal."""

    CEILINGS = {"per_signal": {
        "S1_CREATOR_INITIAL_BUY_PRESENT": {"curves_that_can_produce_a_coordinate": 900,
                                           "of_those_priceable": 800},
        "S2_NO_CREATOR_INITIAL_BUY": {"curves_that_can_produce_a_coordinate": 100,
                                      "of_those_priceable": 90},
        "S3_T0_IS_LAUNCH_INSTRUCTION": {"curves_that_can_produce_a_coordinate": 500,
                                        "of_those_priceable": 400},
        "S4_CASHBACK_ENABLED": {"curves_that_can_produce_a_coordinate": 300,
                                "of_those_priceable": 200},
        "S5_CREATOR_REENTRY_DELAYED_CONFIRMATION": {
            "curves_that_can_produce_a_coordinate": 50, "of_those_priceable": 40},
    }}

    def _grid(self, admitted):
        return {"S1_CREATOR_INITIAL_BUY_PRESENT|h_1000_slots|delay_1|base":
                {"coverage": {"curves_admitted": admitted}}}

    def test_a_cell_within_its_ceiling_is_accepted(self):
        B.assert_ceilings_bind(self.CEILINGS, self._grid(800))

    def test_a_cell_exceeding_its_ceiling_refuses(self):
        """A ceiling that bounds nothing is decoration that reads as a constraint."""
        with self.assertRaisesRegex(B.WindowRefused, "could produce both"):
            B.assert_ceilings_bind(self.CEILINGS, self._grid(801))

    def test_the_complement_partition_holds_when_the_counts_cover_the_cohort(self):
        window = {"features": {f"c{i}": {} for i in range(1000)}}
        got = B.assert_complements_partition(B19D, self.CEILINGS, window)
        self.assertEqual(got["complement_pairs_checked"], 1)

    def test_a_broken_partition_refuses(self):
        window = {"features": {f"c{i}": {} for i in range(1001)}}
        with self.assertRaisesRegex(B.WindowRefused, "complements over"):
            B.assert_complements_partition(B19D, self.CEILINGS, window)

    def test_the_all_zero_case_refuses_rather_than_looking_consistent(self):
        """The exact shape of the feature-block defect: nothing fired, and 0 + 0 agreed.

        A partition check comparing only the two counts to each other passes here. Comparing them
        to the number of curves carrying a block is what catches a study that cannot fire at all.
        """
        ceilings = {"per_signal": dict(self.CEILINGS["per_signal"])}
        for name in ("S1_CREATOR_INITIAL_BUY_PRESENT", "S2_NO_CREATOR_INITIAL_BUY"):
            ceilings["per_signal"][name] = {"curves_that_can_produce_a_coordinate": 0,
                                            "of_those_priceable": 0}
        window = {"features": {f"c{i}": {} for i in range(1000)}}
        with self.assertRaisesRegex(B.WindowRefused, "sum to 0"):
            B.assert_complements_partition(B19D, ceilings, window)

    def test_the_partition_guard_refuses_when_it_finds_nothing_to_check(self):
        """A guard that passes by testing nothing is the failure mode this whole session hunted."""
        class NoComplements:
            SIGNALS = ({"signal_id": "X", "kind": "t0_boolean", "field": "f", "expect": True},)
        with self.assertRaisesRegex(B.WindowRefused, "must not pass by finding nothing"):
            B.assert_complements_partition(NoComplements, {"per_signal": {}}, {"features": {}})


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
