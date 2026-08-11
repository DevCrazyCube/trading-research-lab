"""Guards for the B19N graduated-market collector.

Every test here drives a refusal. That is deliberate and it is the lesson from this collector's
sibling: B11c's ownership guard was CORRECT for a full green run while every fail-open mutation of
it shipped undetected, because the only paths that exercised it drove it in the ALLOW direction. A
guard's failure mode is wrongly-allow, so a suite that never asks it to refuse proves nothing.

This collector needs it more than B11c does. B11c deliberately has no `--work-dir` flag, so its
guard is a backstop behind a config table. B19N KEEPS `--work-dir`, which makes this guard the only
thing between a mistyped command line and an irreplaceable corpus.

No network. Nothing outside a temporary directory is written.
"""
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = _load("b19n_graduated_collector", "b19n_graduated_collector.py")


class WorkDirRefusalTests(unittest.TestCase):
    """MA-ME: the five one-token breaks a peer mutation run found surviving with zero tests."""

    def tmp(self, prefix):
        directory = pathlib.Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, directory, True)
        return directory

    def test_an_exact_forbidden_path_is_refused(self):
        """MA -- drop the `target == owned` arm and this is the hole."""
        with self.assertRaises(C.CollectionRefused):
            C.assert_work_dir_is_ours(ROOT / "research/b11a")

    def test_a_path_inside_a_forbidden_directory_is_refused(self):
        """MB -- drop `owned in target.parents` and a subdirectory walks straight in."""
        with self.assertRaises(C.CollectionRefused):
            C.assert_work_dir_is_ours(ROOT / "research/b11a/logs")

    def test_a_path_containing_a_forbidden_directory_is_refused(self):
        """MC -- drop `target in owned.parents` and `research/` becomes writable."""
        with self.assertRaises(C.CollectionRefused):
            C.assert_work_dir_is_ours(ROOT / "research")

    def test_window_two_is_refused_as_well_as_window_one(self):
        """MD -- an emptied FORBIDDEN_WORK_DIRS must not pass both."""
        with self.assertRaises(C.CollectionRefused):
            C.assert_work_dir_is_ours(ROOT / "research/b11m_window2")

    def test_a_RELATIVE_forbidden_path_is_refused(self):
        """ME -- the mutation absolute-path fixtures cannot see.

        Dropping `.resolve()` leaves every absolute-path test above passing while a relative
        spelling of the same directory sails through. The peer seat found this by mutation after
        pointing out the identical blind spot in B11c's M4: a branch is coverage-invisible until a
        fixture is built in the shape that reaches it.
        """
        for spelling in ("research/b11a", "./research/b11a", "research/b11a/"):
            with self.subTest(spelling=spelling):
                with self.assertRaises(C.CollectionRefused):
                    C.assert_work_dir_is_ours(spelling)

    def test_an_unlisted_precious_directory_is_refused(self):
        """The denylist leak: protection must not depend on being named.

        The first version named only window 1 and window 2, so any other spent corpus was safe only
        by accident of sitting inside `research/`. A directory holding somebody else's work and no
        B19N witness is refused on that basis alone -- which covers corpora that do not exist yet.
        """
        directory = self.tmp("b19n-precious-")
        (directory / "b9d_transaction_bodies.sqlite").write_bytes(b"SQLite format 3\x00")
        with self.assertRaises(C.CollectionRefused) as caught:
            C.assert_work_dir_is_ours(directory)
        self.assertIn("carries no", str(caught.exception))

    def test_a_directory_b19n_already_owns_is_accepted(self):
        """The other direction: the guard must not refuse this collector's own corpus."""
        directory = self.tmp("b19n-own-")
        (directory / "b19n_graduated.sqlite").write_bytes(b"SQLite format 3\x00")
        C.claim_work_dir(directory)
        self.assertEqual(directory.resolve(), C.assert_work_dir_is_ours(directory))

    def test_b19n_output_alone_without_a_witness_is_still_refused(self):
        """A corpus whose witness was deleted is unclaimed, not adopted."""
        directory = self.tmp("b19n-nowitness-")
        (directory / "unrelated_work.sqlite").write_bytes(b"x")
        with self.assertRaises(C.CollectionRefused):
            C.assert_work_dir_is_ours(directory)

    def test_an_empty_directory_is_accepted(self):
        directory = self.tmp("b19n-empty-")
        self.assertEqual(directory.resolve(), C.assert_work_dir_is_ours(directory))

    def test_a_file_where_a_directory_belongs_is_refused(self):
        directory = self.tmp("b19n-file-")
        target = directory / "not-a-dir"
        target.write_text("")
        with self.assertRaises(C.CollectionRefused):
            C.assert_work_dir_is_ours(target)

    def test_refusing_creates_nothing(self):
        """The guard runs BEFORE mkdir, so a rejected path must leave no trace."""
        directory = self.tmp("b19n-notrace-")
        target = directory / "would-be-created" / "deeper"
        (directory / "somebody_elses.sqlite").write_bytes(b"x")
        with self.assertRaises(C.CollectionRefused):
            C.assert_work_dir_is_ours(directory)
        self.assertFalse(target.exists())

    def test_the_rpc_refusal_names_the_variable_and_never_a_file(self):
        directory = self.tmp("b19n-rpc-")
        import os
        saved = os.environ.pop(C.RPC_ENV_VAR, None)
        try:
            with self.assertRaises(C.CollectionRefused) as caught:
                C.rpc_endpoint()
            self.assertIn(C.RPC_ENV_VAR, str(caught.exception))
        finally:
            if saved is not None:
                os.environ[C.RPC_ENV_VAR] = saved


class DepositSpreadTests(unittest.TestCase):
    """The check that caught a float artifact being written down as a protocol constant."""

    def test_a_tight_cluster_reports_clustered(self):
        pools = [{"quote_deposit": C.OBSERVED_DEPOSIT_MIN},
                 {"quote_deposit": C.OBSERVED_DEPOSIT_MAX}]
        self.assertTrue(C.assert_deposit_uniform(pools)["clustered"])

    def test_a_wide_spread_reports_not_clustered_rather_than_dropping_pools(self):
        pools = [{"quote_deposit": 1_000_000_000}, {"quote_deposit": 2_000_000_000}]
        result = C.assert_deposit_uniform(pools)
        self.assertFalse(result["clustered"])
        self.assertIn("re-derive its population", result["note"])

    def test_the_comparison_uses_no_float(self):
        """One lamport outside the tolerance must flip it; a float would round the boundary away."""
        low = 1_000_000_000
        edge = low + (low * C.DEPOSIT_SPREAD_TOLERANCE_PPM) // 1_000_000
        self.assertTrue(C.assert_deposit_uniform(
            [{"quote_deposit": low}, {"quote_deposit": edge}])["clustered"])
        self.assertFalse(C.assert_deposit_uniform(
            [{"quote_deposit": low}, {"quote_deposit": edge + 1}])["clustered"])


class ContainmentIsTheOnlyDefenceWhenTheTargetIsEmptyTests(unittest.TestCase):
    """Reach the containment branch, which the real corpora cannot.

    Driving containment against window 1 proves nothing about containment: window 1 is FULL, so the
    fail-closed rule refuses it whatever the containment arms do. A mutation run confirmed it --
    dropping the `owned in parents` arm, the `target in parents` arm, or `.resolve()` left every
    absolute-path test green, because a different branch was catching the fixture.

    An EMPTY forbidden directory is the only shape that reaches containment, and it is exactly the
    shape a freshly created window has before it collects anything. So the fixtures are synthetic
    forbidden roots, injected.
    """

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="b19n-contain-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.forbidden = ("precious/window",)
        (self.root / "precious" / "window").mkdir(parents=True)   # EMPTY on purpose

    def guard(self, path):
        return C.assert_work_dir_is_ours(path, forbidden=self.forbidden, root=self.root)

    def test_the_exact_empty_forbidden_directory_is_refused(self):
        """MA, reached: nothing else can catch this -- the directory is empty."""
        with self.assertRaises(C.CollectionRefused):
            self.guard(self.root / "precious/window")

    def test_a_path_inside_an_empty_forbidden_directory_is_refused(self):
        """MB, reached."""
        with self.assertRaises(C.CollectionRefused):
            self.guard(self.root / "precious/window/deeper")

    def test_a_path_containing_an_empty_forbidden_directory_is_refused(self):
        """MC, reached."""
        with self.assertRaises(C.CollectionRefused):
            self.guard(self.root / "precious")

    def test_a_relative_spelling_of_an_empty_forbidden_directory_is_refused(self):
        """ME, reached: without .resolve() a relative path is never equal to the absolute one."""
        import os
        saved = os.getcwd()
        os.chdir(self.root)
        try:
            for spelling in ("precious/window", "./precious/window", "precious/window/"):
                with self.subTest(spelling=spelling):
                    with self.assertRaises(C.CollectionRefused):
                        self.guard(spelling)
        finally:
            os.chdir(saved)

    def test_an_unrelated_empty_directory_is_still_accepted(self):
        """The guard must refuse the forbidden tree and nothing else."""
        elsewhere = self.root / "fresh"
        elsewhere.mkdir()
        self.assertEqual(elsewhere.resolve(), self.guard(elsewhere))

    def test_a_witnessed_directory_that_CONTAINS_a_forbidden_one_is_still_refused(self):
        """MC, reached -- the only shape where containment is genuinely the sole defence.

        Any directory containing a forbidden one necessarily has content, so the fail-closed rule
        normally fires first and the `target in owned.parents` arm never gets a turn. That made the
        arm look redundant under mutation. It is not: put B19N's OWN witness in a parent of a
        precious directory -- which a careless re-run of an earlier collection could do -- and
        fail-closed is satisfied, leaving containment alone between `--work-dir` and the corpus
        underneath.

        This is the same lesson as the empty-directory fixtures above, one level further in: a
        branch is not dead because no fixture reaches it, it is untested until one does.
        """
        parent = self.root / "precious"
        C.claim_work_dir(parent)
        self.assertTrue(C.our_witness(parent).exists())
        with self.assertRaises(C.CollectionRefused) as caught:
            self.guard(parent)
        self.assertIn("is, contains, or lies inside", str(caught.exception))
