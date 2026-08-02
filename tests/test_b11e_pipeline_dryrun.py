"""B11e — every check must be able to go red.

A dry run that reports nine passes is only worth the checks that could have failed. Each test here
breaks exactly one invariant and asserts the corresponding check notices. The two regression
classes at the end are real defects this harness found on its first run.
"""
import importlib.util
import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DRY = _load("b11e_pipeline_dryrun", "b11e_pipeline_dryrun.py")
# Reached THROUGH the harness so there is one module graph, not three. Loading b9d a second time by
# path would give this file a different FreezeViolation class than the one the harness raises, and
# every `assertRaises` below would pass or fail for the wrong reason.
B9D = DRY.B9D
B11D = DRY.B11D
B11C = DRY.B11C


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b11e-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.directory, ignore_errors=True))


class TestArgumentChecking(Temp):
    def test_a_flag_the_script_does_not_declare_is_caught(self):
        """The shape of the defect that had `b9d run` silently collecting the burned corpus."""
        argv = [sys.executable, "scripts/b9d_transaction_bodies.py", "run",
                "--no-such-flag", "x"]
        findings = DRY.check_arguments("transaction_bodies", argv)
        self.assertTrue(any("--no-such-flag" in f for f in findings), findings)

    def test_a_subcommand_the_script_does_not_have_is_caught(self):
        argv = [sys.executable, "scripts/b9d_transaction_bodies.py", "notasubcommand"]
        findings = DRY.check_arguments("transaction_bodies", argv)
        self.assertTrue(any("does not exist" in f for f in findings), findings)

    def test_the_real_stage_arguments_are_all_declared(self):
        for stage, command in B11C.stage_commands(self.directory).items():
            with self.subTest(stage=stage):
                self.assertEqual([], DRY.check_arguments(stage, command["argv"]))


class TestIsolation(Temp):
    def test_a_burned_artifact_in_the_arguments_is_caught(self):
        for marker in DRY.BURNED_MARKERS:
            with self.subTest(marker=marker):
                argv = [sys.executable, "scripts/x.py", "--b9a", f"research/{marker}"]
                findings = DRY.check_isolation("transaction_bodies", argv, self.directory)
                self.assertTrue(any(marker in f for f in findings), findings)

    def test_an_artifact_path_outside_the_fixture_is_caught(self):
        argv = [sys.executable, "scripts/x.py", "--out", "/var/tmp/elsewhere.sqlite"]
        findings = DRY.check_isolation("build_cohort", argv, self.directory)
        self.assertTrue(any("outside the fixture" in f for f in findings), findings)

    def test_an_override_equal_to_its_module_default_is_not_an_override(self):
        argv = [sys.executable, "scripts/b9d_transaction_bodies.py", "run",
                "--b9a", B9D.B9A_PATH]
        findings = DRY.check_overrides_differ_from_defaults("transaction_bodies", argv)
        self.assertTrue(any("burned corpus" in f for f in findings), findings)

    def test_a_genuine_override_is_not_flagged(self):
        argv = [sys.executable, "scripts/b9d_transaction_bodies.py", "run",
                "--b9a", str(self.directory / "b11a_cohort.sqlite")]
        self.assertEqual([], DRY.check_overrides_differ_from_defaults("transaction_bodies", argv))


class TestChain(Temp):
    def test_a_stage_reading_what_nothing_produces_is_caught(self):
        original = dict(DRY.STAGE_IO["build_cohort"])
        DRY.STAGE_IO["build_cohort"] = {"reads": ("nobody_writes_this.sqlite",),
                                        "writes": original["writes"]}
        self.addCleanup(lambda: DRY.STAGE_IO.__setitem__("build_cohort", original))
        findings = DRY.check_chain(B11C.stage_commands(self.directory))
        self.assertTrue(any("no earlier stage produces" in f for f in findings), findings)

    def test_a_declared_interface_the_arguments_do_not_match_is_caught(self):
        original = dict(DRY.STAGE_IO["signature_inventory"])
        DRY.STAGE_IO["signature_inventory"] = {"reads": original["reads"],
                                               "writes": ("b11a_cohort.sqlite", "phantom.sqlite")}
        self.addCleanup(lambda: DRY.STAGE_IO.__setitem__("signature_inventory", original))
        findings = DRY.check_chain(B11C.stage_commands(self.directory))
        self.assertTrue(any("phantom.sqlite" in f for f in findings), findings)

    def test_the_real_chain_joins_up(self):
        self.assertEqual([], DRY.check_chain(B11C.stage_commands(self.directory)))

    def test_the_chain_covers_exactly_the_nine_stages_the_watcher_runs(self):
        """If the watcher grew a tenth stage, this audit would quietly stop covering it."""
        self.assertEqual(sorted(DRY.STAGE_IO), sorted(B11C.RUN_ORDER))


class TestGatesDoNotPassVacuously(Temp):
    def test_every_gate_refuses_an_empty_artifact(self):
        DRY.make_enumeration(self.directory / "b11a_creates.sqlite")
        B11D.build(self.directory / "b11a_creates.sqlite", self.directory / "b11a_cohort.sqlite")
        findings, exits = DRY.check_gates_refuse_an_empty_artifact(self.directory)
        self.assertEqual([], findings)
        for stage, code in exits.items():
            with self.subTest(stage=stage):
                self.assertNotEqual(0, code, f"{stage} passed on an artifact containing nothing")


class TestOffline(Temp):
    def test_an_inherited_rpc_credential_is_caught(self):
        import os
        os.environ["SOLANA_RPC_URL"] = "https://should-not-be-here.invalid/"
        self.addCleanup(lambda: os.environ.pop("SOLANA_RPC_URL", None))
        findings = DRY.check_offline(self.directory)
        self.assertTrue(any("proved nothing" in f for f in findings), findings)


class TestRefusalTypes(Temp):
    """The two real defects this harness found. Both are the same mistake in two places.

    A refusal raised as something other than the project's refusal type is not fail-closed: the
    handler written to contain it does not apply, and the failure arrives as a traceback from a
    layer that had a perfectly good error message ready for it.
    """

    def test_a_missing_source_is_refused_as_a_refusal(self):
        with self.assertRaises(B9D.FreezeViolation):
            B9D.sha256_file(str(self.directory / "not_here.sqlite"))

    def test_a_missing_cohort_is_refused_as_a_cohort_refusal(self):
        with self.assertRaises(B11D.CohortRefused):
            B11D.assert_fresh_cohort(self.directory / "not_here.sqlite")

    def test_b9ds_wrapper_around_a_missing_cohort_now_applies(self):
        """The wrapper existed; it just did not catch the most ordinary bad cohort of all."""
        with self.assertRaises(B9D.FreezeViolation):
            B9D.assert_sources(str(self.directory / "a.sqlite"), str(self.directory / "b.sqlite"))

    def test_a_readable_file_still_hashes(self):
        target = self.directory / "readable"
        target.write_bytes(b"abc")
        self.assertEqual(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            B9D.sha256_file(str(target)))


class TestTheDryRunItself(Temp):
    def test_it_passes_end_to_end_and_touches_nothing_live(self):
        live = ROOT / "research" / "b11a"
        before = sorted(p.name for p in live.iterdir()) if live.exists() else []
        report = DRY.dry_run(self.directory / "run")
        after = sorted(p.name for p in live.iterdir()) if live.exists() else []
        self.assertEqual(before, after, "the dry run wrote into the live watcher's directory")
        self.assertEqual([], report["findings"])
        self.assertTrue(report["passed"])
        self.assertEqual(list(B11C.RUN_ORDER), report["stages"])
        self.assertFalse(report["network_reachable"])
        self.assertFalse(report["composition_published"])

    def test_it_publishes_no_cohort_composition(self):
        """A count of members built from a synthetic fixture is not fresh-window composition.

        Guarded anyway: the fixture's counts are the harness's own, and nothing that came from the
        live window may appear in a report that gets pasted into a handoff.
        """
        report = DRY.dry_run(self.directory / "run")
        self.assertEqual(3, report["cohort_members_built"])
        text = str(report)
        for burned in DRY.BURNED_MARKERS:
            self.assertNotIn(burned, text)

    def test_the_fixture_directory_is_removed_when_the_harness_owns_it(self):
        seen = {}
        original = DRY.tempfile.mkdtemp

        def spy(**kwargs):
            seen["path"] = original(**kwargs)
            return seen["path"]

        DRY.tempfile.mkdtemp = spy
        self.addCleanup(lambda: setattr(DRY.tempfile, "mkdtemp", original))
        DRY.dry_run()
        self.assertFalse(pathlib.Path(seen["path"]).exists())


if __name__ == "__main__":
    unittest.main()
