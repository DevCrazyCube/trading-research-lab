"""B15k tests. The distinction that matters is lag versus miss, and it is driven both ways.

An absence outside a closed interval means the recorder has not arrived. An absence inside one
means it arrived and saw nothing. Confusing them once marked 112 launches orphaned, so both cases
are constructed here rather than reasoned about.
"""
import hashlib
import importlib.util
import json
import pathlib
import shutil
import sqlite3
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


B15K = _load("b15k_coverage_audit", "b15k_coverage_audit.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15k_"))
        self.document = B15K.verify_preregistration()
        self.b15i = self.directory / "processed_feed.sqlite"
        self.b15a = self.directory / "shadow.sqlite"

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def write_b15i(self, rows):
        connection = sqlite3.connect(self.b15i)
        connection.execute("CREATE TABLE IF NOT EXISTS observation("
                           "signature TEXT PRIMARY KEY, t0_slot INTEGER)")
        connection.executemany("INSERT OR REPLACE INTO observation VALUES (?,?)", rows)
        connection.commit()
        connection.close()

    def write_b15a(self, launches=(), events=()):
        connection = sqlite3.connect(self.b15a)
        connection.execute("CREATE TABLE IF NOT EXISTS launch("
                           "signature TEXT, slot INTEGER, decode_status TEXT)")
        connection.execute("CREATE TABLE IF NOT EXISTS pump_event("
                           "signature TEXT, slot INTEGER)")
        connection.executemany("INSERT INTO launch VALUES (?,?,?)", launches)
        connection.executemany("INSERT INTO pump_event VALUES (?,?)", events)
        connection.commit()
        connection.close()

    def audit(self, **kwargs):
        return B15K.audit(document=self.document, b15i_path=self.b15i, b15a_path=self.b15a,
                          work_dir=self.directory / "out", query=False, **kwargs)


class TestPreregistration(Base):
    def test_the_freeze_is_pinned(self):
        self.assertEqual(self.document["preregistration_id"], "B15K_COVERAGE_AUDIT_V1")
        self.assertTrue(self.document["committed_before_any_comparison"])

    def test_a_tampered_freeze_refuses(self):
        altered = self.directory / "altered.json"
        document = json.loads(B15K.PREREG_PATH.read_bytes())
        document["independent_confirmation_sample"]["sample_size"] = 99999
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15K.CoverageRefused) as caught:
            B15K.verify_preregistration(altered)
        self.assertIn("pinned", str(caught.exception))

    def test_an_unreadable_freeze_refuses(self):
        with self.assertRaises(B15K.CoverageRefused) as caught:
            B15K.verify_preregistration(self.directory / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15K.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        poisoned = self.directory / "poisoned.py"
        poisoned.write_text("EXECUTION_SURFACE_TOKENS = ()\nx = 'sendTransaction'\n")
        with self.assertRaises(B15K.CoverageRefused) as caught:
            B15K.assert_no_execution_surface(poisoned)
        self.assertIn("sendTransaction", str(caught.exception))


class TestCommonInterval(Base):
    def test_the_interval_is_inside_both_extents_by_the_margin(self):
        low, high = B15K.common_closed_interval((1000, 5000), (900, 4000), 300)
        self.assertEqual((low, high), (1300, 3700))

    def test_no_overlap_refuses_rather_than_comparing(self):
        with self.assertRaises(B15K.CoverageRefused) as caught:
            B15K.common_closed_interval((5000, 6000), (1000, 2000), 300)
        self.assertIn(B15K.K_INTERVAL_EMPTY, str(caught.exception))
        self.assertIn("report it as a miss", str(caught.exception))

    def test_an_overlap_smaller_than_the_margins_refuses(self):
        with self.assertRaises(B15K.CoverageRefused) as caught:
            B15K.common_closed_interval((1000, 2000), (1900, 3000), 300)
        self.assertIn(B15K.K_INTERVAL_EMPTY, str(caught.exception))

    def test_a_recorder_with_no_slots_refuses(self):
        with self.assertRaises(B15K.CoverageRefused) as caught:
            B15K.common_closed_interval((None, None), (1000, 2000), 300)
        self.assertIn(B15K.K_INTERVAL_EMPTY, str(caught.exception))

    def test_the_extent_is_the_maximum_across_tables(self):
        """A recorder that saw a million trades and no launches has still reached that slot."""
        self.write_b15a(launches=[("A", 1000, "decoded")], events=[("B", 9000)])
        connection = sqlite3.connect(f"file:{self.b15a}?mode=ro", uri=True)
        extent = B15K.recorder_extent(connection, ("SELECT MIN(slot), MAX(slot) FROM launch",
                                                   "SELECT MIN(slot), MAX(slot) FROM pump_event"))
        connection.close()
        self.assertEqual(extent, (1000, 9000))

    def test_a_missing_table_does_not_sink_the_extent(self):
        self.write_b15a(launches=[("A", 1000, "decoded")])
        connection = sqlite3.connect(f"file:{self.b15a}?mode=ro", uri=True)
        extent = B15K.recorder_extent(connection, ("SELECT MIN(slot), MAX(slot) FROM launch",
                                                   "SELECT MIN(x), MAX(x) FROM nonexistent"))
        connection.close()
        self.assertEqual(extent, (1000, 1000))

    def test_an_unreadable_recorder_refuses(self):
        with self.assertRaises(B15K.CoverageRefused) as caught:
            B15K._read_only(self.directory / "nothing.sqlite")
        self.assertIn(B15K.K_RECORDER_UNREADABLE, str(caught.exception))


class TestClassification(Base):
    def setUp(self):
        super().setUp()
        self.launches = {"decoded_one": "decoded", "failed_one": "decode_failed"}
        self.events = {"event_only"}
        self.interval = (1000, 2000)

    def test_a_decoded_peer_row_is_corroborated(self):
        self.assertEqual(
            B15K.classify("decoded_one", 1500, self.interval, self.launches, self.events),
            B15K.CORROBORATED)

    def test_a_failed_decode_is_its_own_class(self):
        """The frame arrived and the recorder could not read it. That is not a miss."""
        self.assertEqual(
            B15K.classify("failed_one", 1500, self.interval, self.launches, self.events),
            B15K.B15A_DECODE_FAILED)

    def test_a_non_launch_only_row_is_its_own_class(self):
        self.assertEqual(
            B15K.classify("event_only", 1500, self.interval, self.launches, self.events),
            B15K.B15A_SAW_NON_LAUNCH)

    def test_an_absence_is_named_an_absence_and_never_an_orphan(self):
        label = B15K.classify("nowhere", 1500, self.interval, self.launches, self.events)
        self.assertEqual(label, B15K.ABSENT_FROM_B15A)
        self.assertNotIn("ORPHAN", label)
        self.assertNotIn("FORK", label)

    def test_outside_the_interval_is_refused_not_classified(self):
        """Lag, not miss. Below the low edge and above the high edge both refuse."""
        for slot in (999, 2001):
            with self.assertRaises(B15K.CoverageRefused) as caught:
                B15K.classify("nowhere", slot, self.interval, self.launches, self.events)
            self.assertIn(B15K.K_OUTSIDE_INTERVAL, str(caught.exception))

    def test_the_interval_edges_are_inclusive(self):
        for slot in (1000, 2000):
            self.assertEqual(
                B15K.classify("nowhere", slot, self.interval, self.launches, self.events),
                B15K.ABSENT_FROM_B15A)

    def test_a_decoded_row_wins_over_a_failed_row_for_the_same_signature(self):
        self.write_b15a(launches=[("S", 1500, "decode_failed"), ("S", 1500, "decoded")])
        connection = sqlite3.connect(f"file:{self.b15a}?mode=ro", uri=True)
        launches, _events = B15K.b15a_index(connection)
        connection.close()
        self.assertEqual(launches["S"], "decoded")


class TestLagVersusMiss(Base):
    def test_a_launch_the_peer_has_not_reached_is_excluded_not_counted_as_missing(self):
        """The whole point. B15a 500 slots behind must not manufacture 1,935 misses."""
        self.write_b15i([(f"S{i}", 10_000 + i) for i in range(50)])
        self.write_b15a(launches=[], events=[("E", 9_000)])          # peer stops well short
        with self.assertRaises(B15K.CoverageRefused) as caught:
            self.audit()
        self.assertIn(B15K.K_INTERVAL_EMPTY, str(caught.exception))

    def test_a_launch_the_peer_passed_and_never_recorded_is_counted_as_absent(self):
        # The B15i span must itself be wider than twice the margin, or no closed interval exists.
        self.write_b15i([("Low", 6_000), ("S1", 10_000), ("High", 15_000)])
        self.write_b15a(launches=[], events=[("E", 5_000), ("E2", 20_000)])
        report = self.audit()
        self.assertEqual(report["common_closed_interval"], [6_300, 14_700])
        self.assertEqual(report["classes"], {B15K.ABSENT_FROM_B15A: 1})   # only S1 is inside

    def test_only_launches_inside_the_interval_are_compared(self):
        self.write_b15i([("Early", 5_100), ("Middle", 10_000), ("Late", 19_900)])
        self.write_b15a(launches=[("Middle", 10_000, "decoded")],
                        events=[("E", 5_000), ("E2", 20_000)])
        report = self.audit()
        self.assertEqual(report["common_closed_interval"], [5_400, 19_600])
        self.assertEqual(report["comparable_launches"], 1)     # Early and Late sit on the edges
        self.assertEqual(report["classes"], {B15K.CORROBORATED: 1})


class TestSample(Base):
    def test_the_sample_is_deterministic(self):
        population = [f"Sig{i:04d}" for i in range(500)]
        first = B15K.select_sample(population, 200)
        second = B15K.select_sample(list(reversed(population)), 200)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 200)

    def test_the_sample_is_ordered_by_hash_not_by_name(self):
        population = [f"Sig{i:04d}" for i in range(100)]
        sample = B15K.select_sample(population, 10)
        self.assertNotEqual(sample, sorted(population)[:10])
        expected = sorted(population, key=lambda s: hashlib.sha256(s.encode()).hexdigest())[:10]
        self.assertEqual(sample, expected)

    def test_a_population_smaller_than_the_sample_is_taken_whole(self):
        self.assertEqual(len(B15K.select_sample(["a", "b"], 200)), 2)

    def test_duplicates_do_not_inflate_the_sample(self):
        self.assertEqual(B15K.select_sample(["a", "a", "b"], 200), sorted(
            ["a", "b"], key=lambda s: hashlib.sha256(s.encode()).hexdigest()))


class TestConclusion(Base):
    def test_all_confirmed_means_the_peer_under_records(self):
        conclusion = B15K.conclude({B15K.CONFIRMED_ON_CHAIN: 200})
        self.assertIn("b15a_under_records", conclusion)
        self.assertIn("sole confirmation oracle", conclusion)

    def test_all_absent_means_processed_only(self):
        self.assertIn("processed_only", B15K.conclude({B15K.NOT_FOUND_AT_CONFIRMED: 200}))

    def test_a_split_asserts_neither_explanation(self):
        conclusion = B15K.conclude({B15K.CONFIRMED_ON_CHAIN: 100,
                                    B15K.NOT_FOUND_AT_CONFIRMED: 100})
        self.assertIn("mixed", conclusion)
        self.assertIn("no single explanation", conclusion)

    def test_failures_alone_decide_nothing(self):
        self.assertIn("undecided", B15K.conclude({B15K.QUERY_FAILED: 200}))

    def test_a_failed_query_never_counts_as_evidence_either_way(self):
        outcomes = {B15K.CONFIRMED_ON_CHAIN: 190, B15K.QUERY_FAILED: 10}
        self.assertIn("b15a_under_records", B15K.conclude(outcomes))


class TestConfirmation(Base):
    def _opener(self, result):
        def opener(request, timeout=None):
            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()
        return opener

    def _exchanges(self):
        B15B = B15K.B15B
        return B15B.ExchangeLog(self.directory / "rpc_exchanges.jsonl")

    def _policy(self):
        return self.document["independent_confirmation_sample"]["query"]

    def test_a_present_transaction_is_confirmed_on_chain(self):
        outcome, _payload = B15K.confirm_signature(
            "S", "https://x.invalid", self._policy(), self._exchanges(),
            self._opener({"slot": 1}), lambda _s: None)
        self.assertEqual(outcome, B15K.CONFIRMED_ON_CHAIN)

    def test_a_null_result_is_not_found_at_confirmed(self):
        outcome, _payload = B15K.confirm_signature(
            "S", "https://x.invalid", self._policy(), self._exchanges(),
            self._opener(None), lambda _s: None)
        self.assertEqual(outcome, B15K.NOT_FOUND_AT_CONFIRMED)

    def test_a_dead_endpoint_is_a_failure_not_an_absence(self):
        def opener(request, timeout=None):
            raise OSError("endpoint down")

        outcome, _payload = B15K.confirm_signature(
            "S", "https://x.invalid", self._policy(), self._exchanges(), opener, lambda _s: None)
        self.assertEqual(outcome, B15K.QUERY_FAILED)

    def test_the_query_is_bounded_by_max_attempts(self):
        calls = []

        def opener(request, timeout=None):
            calls.append(1)
            raise OSError("endpoint down")

        B15K.confirm_signature("S", "https://x.invalid", self._policy(), self._exchanges(),
                               opener, lambda _s: None)
        self.assertEqual(len(calls), self._policy()["max_attempts_per_signature"])

    def test_the_raw_exchange_is_written_before_the_answer_is_judged(self):
        B15K.confirm_signature("S", "https://x.invalid", self._policy(), self._exchanges(),
                               self._opener({"slot": 1}), lambda _s: None)
        lines = (self.directory / "rpc_exchanges.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["signature"], "S")

    def test_the_query_asks_at_confirmed_commitment(self):
        seen = {}

        def opener(request, timeout=None):
            seen.update(json.loads(request.data))

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps({"result": {"slot": 1}}).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        B15K.confirm_signature("S", "https://x.invalid", self._policy(), self._exchanges(),
                               opener, lambda _s: None)
        self.assertEqual(seen["method"], "getTransaction")
        self.assertEqual(seen["params"][1]["commitment"], "confirmed")


class TestReportShape(Base):
    def test_the_report_carries_the_conditional_coverage_statement(self):
        self.write_b15i([("Low", 6_000), ("S1", 10_000), ("High", 15_000)])
        self.write_b15a(launches=[], events=[("E", 5_000), ("E2", 20_000)])
        report = self.audit()
        self.assertIn("conditional on the observing feed", report["coverage_statement"])
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        text = json.dumps(report).lower()
        for banned in ("profit", "pnl", "roi", "landing_probability"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
