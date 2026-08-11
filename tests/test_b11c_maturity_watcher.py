"""Tests for the B11c maturity watcher and collection supervisor.

Nothing here touches a network. Every RPC call goes through an injected fake transport and every
stage through an injected fake runner, so the whole state machine — including maturity, retries,
quarantine and resume — is exercised without a single real request.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import sys
import time
import unittest
import urllib.error
import ssl
import io

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("b11c_maturity_watcher", "b11c_maturity_watcher.py")
B11A = W.B11A

CUTOFF = B11A.derive_window()["observation_cutoff_slot_inclusive"]
URL = "https://rpc.invalid/?api-key=SECRETVALUE1234567890"


class Harness:
    """A temporary B11a directory with fake transport and runner."""

    def __init__(self, test, tips, stage_exit=0):
        self.test = test
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-"))
        test.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.tips = list(tips)
        self.calls = []
        self.stage_exit = stage_exit
        self.ran = []
        self.slept = []

    @property
    def paths(self):
        return {"work_dir": self.directory, "state_path": self.directory / "state.json",
                "receipt_dir": self.directory / "receipts", "log_dir": self.directory / "logs"}

    def transport(self, url, method, params):
        self.calls.append((url, method, params))
        return self.tips.pop(0) if self.tips else self.tips_default

    tips_default = 0

    def sleeper(self, seconds):
        self.slept.append(seconds)

    def runner(self, argv, stdout_path, stderr_path):
        self.ran.append(argv)
        pathlib.Path(stdout_path).write_text("stage output\n")
        pathlib.Path(stderr_path).write_text("")
        return self.stage_exit

    def resolved_commands(self):
        """The real argv, with every stage declared resolved. Lets the state machine be driven end
        to end without pretending the real pipeline is wired."""
        commands = W.stage_commands(self.directory)
        return {name: dict(command, wiring="resolved") for name, command in commands.items()}

    def watch(self, **kwargs):
        options = dict(self.paths)
        options.update(kwargs)
        return W.watch(URL, transport=self.transport, sleeper=self.sleeper, runner=self.runner,
                       **options)

    def watch_all(self, **kwargs):
        return self.watch(commands=self.resolved_commands(), **kwargs)


# --------------------------------------------------------------------------------------------

class MaturityTests(unittest.TestCase):
    """One slot early is early, and only a finalized slot counts."""

    def test_one_slot_before_the_cutoff_starts_nothing(self):
        harness = Harness(self, [CUTOFF - 1])
        state = harness.watch(poll_seconds=1, max_iterations=1)
        self.assertEqual(state["state"], W.STATE_WAITING)
        self.assertEqual(harness.ran, [])

    def test_exactly_the_cutoff_is_mature(self):
        harness = Harness(self, [CUTOFF])
        state = harness.watch_all(poll_seconds=1, max_iterations=1)
        self.assertEqual(state["state"], W.STATE_ALL_STAGES_COMPLETE)

    def test_at_maturity_the_real_pipeline_runs_every_stage_in_order(self):
        """Every stage is wired now. The A2 probe first, then the enumeration, then the cohort
        adapter that the two repaired stages consume."""
        harness = Harness(self, [CUTOFF])
        harness.watch(poll_seconds=1, max_iterations=1)
        scripts = [argv[1] for argv in harness.ran]
        self.assertEqual(scripts[:3], ["scripts/b9d_transaction_bodies.py",
                                       "scripts/b7d_create_enumerator.py",
                                       "scripts/b11d_cohort_adapter.py"])
        self.assertEqual(len(scripts), len(W.RUN_ORDER))

    def test_the_maturity_test_is_b11as_own(self):
        self.assertFalse(B11A.maturity(CUTOFF - 1)["mature"])
        self.assertTrue(B11A.maturity(CUTOFF)["mature"])
        self.assertTrue(B11A.maturity(CUTOFF + 1)["mature"])

    def test_the_poll_asks_for_a_finalized_slot(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        url, method, params = harness.calls[0]
        self.assertEqual(method, "getSlot")
        self.assertEqual(params, [{"commitment": "finalized"}])

    def test_a_non_integer_tip_is_quarantined(self):
        """A processed or confirmed slot can be rolled back; a tip that is not a slot is not a
        tip."""
        for value in ("437211659", None, -1, True, 1.0):
            with self.subTest(value=value):
                with self.assertRaisesRegex(W.Quarantined, W.Q04_NON_FINALIZED_SLOT):
                    W.poll_finalized_slot(URL, transport=lambda *_a: value)

    def test_waiting_does_not_run_a_stage_however_many_polls(self):
        harness = Harness(self, [CUTOFF - 5, CUTOFF - 4, CUTOFF - 3])
        harness.watch(poll_seconds=1, max_iterations=3)
        self.assertEqual(harness.ran, [])
        self.assertEqual(len(harness.calls), 3)


class AllowlistTests(unittest.TestCase):
    """One method. Everything else is refused for not being it."""

    def test_the_allowlist_holds_only_get_slot(self):
        self.assertEqual(B11A.PREFLIGHT_ALLOWED_METHODS, ("getSlot",))

    def test_every_other_method_is_refused(self):
        for method in ("getSignaturesForAddress", "getBlock", "getProgramAccounts",
                       "getTransaction", "getAccountInfo", "sendTransaction"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(B11A.WindowRefused, "preflight allowlist"):
                    B11A.preflight_call(URL, method, [], transport=lambda *_a: 1)

    def test_the_watcher_never_calls_anything_else(self):
        harness = Harness(self, [CUTOFF - 1, CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=2)
        self.assertEqual({method for _, method, _ in harness.calls}, {"getSlot"})


class VerificationTests(unittest.TestCase):
    """Nothing starts until the frozen inputs are exactly what they were."""

    def test_the_shipped_preregistration_verifies(self):
        window = W.verify_preregistration()
        self.assertEqual(window["cutoff_slot_inclusive"], CUTOFF)
        self.assertEqual(window["preregistration_canonical_sha256"],
                         B11A.PREREGISTRATION_CANONICAL_SHA256)

    def test_the_manifest_covers_every_stage_script_and_pinned_idl(self):
        manifest = W.build_manifest()
        for relative in ("scripts/b7d_create_enumerator.py", "scripts/b9c_signature_inventory.py",
                         "scripts/b9d_transaction_bodies.py", "scripts/b9e_reserve_coverage.py",
                         "scripts/b9f_failure_coverage.py", "scripts/b10a_simulator_kernel.py",
                         "research/pump_idl_9c82f61.json",
                         "research/pump_amm_idl_9c82f61.json"):
            with self.subTest(relative=relative):
                self.assertIn(relative, manifest)

    def test_the_manifest_pins_the_supervisor_itself(self):
        """The blind spot until it was listed: the file that decides which stages run."""
        self.assertIn("scripts/b11c_maturity_watcher.py", W.MANIFEST_FILES)
        self.assertIn("scripts/b11c_maturity_watcher.py", W.build_manifest())

    def test_an_edit_to_the_supervisor_during_the_wait_quarantines_it(self):
        """Self-drift, driven rather than argued.

        The supervisor attests, waits, then reads disk again at the maturity transition and launches
        the stages. If its OWN code changed in between, the stages it runs are not the stages it
        attested, and it must stop. This is the same gap as `test_drift_during_the_wait...` but for
        the one file that check could not see until the self-pin existed.
        """
        harness = Harness(self, [CUTOFF - 1, CUTOFF])
        real_build = W.build_manifest
        self.addCleanup(lambda: setattr(W, "build_manifest", real_build))

        def edit_the_supervisor_while_it_sleeps(seconds):
            harness.slept.append(seconds)
            W.build_manifest = lambda files=W.MANIFEST_FILES: dict(
                real_build(files), **{"scripts/b11c_maturity_watcher.py": "0" * 64})

        harness.sleeper = edit_the_supervisor_while_it_sleeps
        with self.assertRaisesRegex(W.Quarantined, W.Q02_SCRIPT_MANIFEST_DRIFT):
            harness.watch(poll_seconds=1)
        self.assertEqual([], harness.ran,
                         "a stage ran under a supervisor whose own code the run never attested")
        state = json.loads(harness.paths["state_path"].read_text())
        self.assertEqual(W.STATE_QUARANTINED, state["state"])

    def test_an_unchanged_supervisor_reaches_its_stages(self):
        """The other half: self-pinning must not quarantine a run that held still."""
        harness = Harness(self, [CUTOFF - 1, CUTOFF])
        state = harness.watch(poll_seconds=1)
        self.assertEqual(W.STATE_ALL_STAGES_COMPLETE, state["state"])
        self.assertEqual(len(W.RUN_ORDER), len(harness.ran))
        self.assertEqual(W.manifest_hash(W.build_manifest()), state["manifest_sha256"])

    def test_a_missing_manifest_file_stops_everything(self):
        with self.assertRaisesRegex(W.WatcherRefused, W.Q02_SCRIPT_MANIFEST_DRIFT):
            W.build_manifest(("scripts/does-not-exist.py",))

    def test_manifest_drift_quarantines_a_resumed_run(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        state = json.loads(harness.paths["state_path"].read_text())
        state["manifest_sha256"] = "0" * 64
        harness.paths["state_path"].write_text(json.dumps(state))
        with self.assertRaisesRegex(W.Quarantined, W.Q02_SCRIPT_MANIFEST_DRIFT):
            Harness(self, [CUTOFF - 1]).watch(
                poll_seconds=1, max_iterations=1, **{k: v for k, v in harness.paths.items()})

    def test_drift_during_the_wait_quarantines_before_any_stage_runs(self):
        """The gap the start-of-run check cannot see.

        A run attests its manifest, waits days for maturity, then executes the stages as
        subprocesses that read whatever is on disk by then. Checking only at start attests the
        scripts present when the WAITING began. An edit landing during the wait used to be
        collected under, and attested away by, a digest describing different code.
        """
        harness = Harness(self, [CUTOFF - 1, CUTOFF])
        real_build = W.build_manifest
        self.addCleanup(lambda: setattr(W, "build_manifest", real_build))

        def drift_while_it_sleeps(seconds):
            harness.slept.append(seconds)
            W.build_manifest = lambda files=W.MANIFEST_FILES: dict(real_build(files),
                                                                   **{"scripts/edited.py": "0" * 64})

        harness.sleeper = drift_while_it_sleeps
        with self.assertRaisesRegex(W.Quarantined, W.Q02_SCRIPT_MANIFEST_DRIFT):
            harness.watch(poll_seconds=1)
        self.assertEqual([], harness.ran, "a stage ran under scripts the run never attested")
        state = json.loads(harness.paths["state_path"].read_text())
        self.assertEqual(W.STATE_QUARANTINED, state["state"])

    def test_a_run_whose_scripts_hold_still_reaches_its_stages(self):
        """The other half: the new check must not quarantine a run that did nothing wrong."""
        harness = Harness(self, [CUTOFF - 1, CUTOFF])
        state = harness.watch(poll_seconds=1)
        self.assertEqual(W.STATE_ALL_STAGES_COMPLETE, state["state"])
        self.assertEqual(len(W.RUN_ORDER), len(harness.ran))

    def test_preregistration_drift_quarantines_a_resumed_run(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        state = json.loads(harness.paths["state_path"].read_text())
        state["preregistration_canonical_sha256"] = "0" * 64
        harness.paths["state_path"].write_text(json.dumps(state))
        with self.assertRaisesRegex(W.Quarantined, W.Q01_PREREGISTRATION_DRIFT):
            Harness(self, [CUTOFF - 1]).watch(
                poll_seconds=1, max_iterations=1, **{k: v for k, v in harness.paths.items()})

    def test_a_document_whose_endpoints_disagree_with_the_register_is_refused(self):
        """By B11a's own `assert_matches_preregistration`, which is exactly this comparison. The
        watcher does not repeat it: a second check that only fires when the first already has is a
        check nobody can show works."""
        document = B11A.load_preregistration()
        for field in ("launch_window_first_slot_inclusive", "launch_window_last_slot_inclusive",
                      "observation_cutoff_slot_inclusive"):
            with self.subTest(field=field):
                doctored = json.loads(json.dumps(document))
                doctored["frozen_window"][field] += 1
                with self.assertRaises(B11A.WindowRefused):
                    W.verify_preregistration(doctored)

    def test_a_preregistration_with_no_commit_is_quarantined(self):
        class Result:
            stdout = ""
            returncode = 0
        with self.assertRaisesRegex(W.Quarantined, "no commit"):
            W.verify_git_ancestry(git=lambda *_a: Result())

    def test_a_preregistration_that_is_not_an_ancestor_is_quarantined(self):
        class Found:
            stdout = "abc123\n"
            returncode = 0

        class NotAncestor:
            stdout = ""
            returncode = 1

        def git(*args):
            return Found() if args[0] == "log" else NotAncestor()

        with self.assertRaisesRegex(W.Quarantined, W.Q03_GIT_ANCESTRY_BROKEN):
            W.verify_git_ancestry(git=git)

    def test_the_git_ancestry_of_the_preregistration_is_checked(self):
        result = W.verify_git_ancestry()
        self.assertTrue(result["preregistration_commit"])
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", result["preregistration_commit"], "HEAD"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(ancestry.returncode, 0)


class StageOrderTests(unittest.TestCase):
    """The A2 probe first, results stages never."""

    def test_the_a2_probe_runs_first(self):
        """An upgrade boundary is a property of the program, so it costs no composition — and if
        version coverage cannot be proven there is nothing worth collecting."""
        self.assertEqual(W.RUN_ORDER[0], "program_boundary")
        self.assertEqual(W.verify_stage_order()[0], "program_boundary")

    def test_every_stage_is_a_frozen_permitted_stage_or_a_declared_local_one(self):
        known = {stage["stage"]: stage for stage in B11A.PIPELINE}
        for name in W.RUN_ORDER:
            with self.subTest(stage=name):
                if name in W.LOCAL_STAGES:
                    continue
                self.assertIn(name, known)
                self.assertTrue(known[name]["permitted_before_unlock"])

    def test_no_results_stage_can_be_scheduled(self):
        for name in ("position_paths", "outcome_labels"):
            with self.subTest(stage=name):
                self.assertIn(name, W.FORBIDDEN_STAGES)
                self.assertNotIn(name, W.RUN_ORDER)
                with self.assertRaises(B11A.WindowRefused):
                    B11A.assert_stage_permitted(name, mature=True, results_unlocked=False)

    def test_no_stage_appears_twice(self):
        self.assertEqual(len(set(W.RUN_ORDER)), len(W.RUN_ORDER))

    def test_every_order_rule_is_reachable(self):
        """Driven by injection. With the shipped tuple every one of these is unreachable, and an
        unreachable check is one nobody can show works."""
        good = list(W.RUN_ORDER)
        cases = {
            "must run first": ["enumerate_creates", "program_boundary"] + good[2:],
            "appears twice": good + [good[1]],
            "may never be scheduled": good + ["position_paths"],
            "nor a declared local stage": good + ["invented_stage"],
        }
        for expected, order in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(B11A.WindowRefused, expected):
                    W.verify_stage_order(order)

    def test_a_results_stage_is_refused_for_being_results_before_anything_else(self):
        with self.assertRaisesRegex(B11A.WindowRefused, "may never be scheduled"):
            W.verify_stage_order(["position_paths"] + list(W.RUN_ORDER))

    def test_the_forbidden_declaration_must_match_the_frozen_pipeline(self):
        """A declaration that has drifted from what it describes is worse than none: it reads like
        a guarantee and guarantees nothing."""
        self.assertEqual(
            tuple(W.FORBIDDEN_STAGES),
            tuple(stage["stage"] for stage in B11A.PIPELINE
                  if not stage["permitted_before_unlock"]))
        original = W.FORBIDDEN_STAGES
        try:
            W.FORBIDDEN_STAGES = ("position_paths",)
            with self.assertRaisesRegex(B11A.WindowRefused, "has drifted from what it describes"):
                W.verify_stage_order()
        finally:
            W.FORBIDDEN_STAGES = original

    def test_the_stages_run_in_order_and_once_each(self):
        harness = Harness(self, [CUTOFF])
        harness.watch_all(poll_seconds=1, max_iterations=1)
        ran = [argv[1] for argv in harness.ran]
        self.assertEqual(len(ran), len(W.RUN_ORDER))
        self.assertEqual(ran[0], "scripts/b9d_transaction_bodies.py")
        self.assertEqual(harness.ran[0][2], "collect-boundary")

    def test_a_stage_with_a_receipt_is_never_rerun(self):
        harness = Harness(self, [CUTOFF])
        harness.watch_all(poll_seconds=1, max_iterations=1)
        first = len(harness.ran)
        second = Harness(self, [CUTOFF])
        second.directory = harness.directory
        second.ran = harness.ran
        second.watch_all(poll_seconds=1, max_iterations=1)
        self.assertEqual(len(harness.ran), first)

    def test_running_a_stage_twice_directly_is_refused(self):
        harness = Harness(self, [CUTOFF])
        harness.watch_all(poll_seconds=1, max_iterations=1)
        state = json.loads(harness.paths["state_path"].read_text())
        commands = harness.resolved_commands()
        with self.assertRaisesRegex(W.Quarantined, W.Q12_DUPLICATE_STAGE):
            W.run_stage("program_boundary", commands["program_boundary"], state,
                        runner=harness.runner, log_dir=harness.paths["log_dir"],
                        receipt_dir=harness.paths["receipt_dir"],
                        state_path=harness.paths["state_path"])


class WiringTests(unittest.TestCase):
    """A stage that cannot be pointed at the B11a directory is quarantined, not guessed at."""

    def test_the_planner_reports_the_pipeline_ready(self):
        plan = W.dry_run_plan()
        self.assertEqual(plan["stages_unresolved"], [])
        self.assertTrue(plan["launch_ready_for_collection"])

    def test_an_unresolved_stage_is_reported_by_the_planner(self):
        """Every stage is resolved today, so the reporter is driven with an injected unresolved
        command — otherwise the function that decides launch-readiness is never exercised on the
        case it exists for."""
        commands = W.stage_commands(pathlib.Path("/tmp/b11a-iso"))
        commands["transaction_bodies"] = dict(commands["transaction_bodies"],
                                              wiring="unresolved")
        self.assertEqual(W.unresolved_stages(commands), ["transaction_bodies"])
        self.assertEqual(W.unresolved_stages(W.stage_commands(pathlib.Path("/tmp/b11a-iso"))), [])

    def test_the_cohort_adapter_runs_before_the_stages_that_consume_it(self):
        order = list(W.RUN_ORDER)
        self.assertLess(order.index("enumerate_creates"), order.index("build_cohort"))
        self.assertLess(order.index("build_cohort"), order.index("signature_inventory"))
        self.assertLess(order.index("build_cohort"), order.index("transaction_bodies"))

    def test_every_consumer_is_pointed_at_the_study_population(self):
        """The subsample, not the full cohort, and not the burned corpus.

        The full cohort is the sampling FRAME; the subsample is the population actually studied.
        A consumer left on the frame would carry 33,866 curves against an inventory covering
        5,000 -- and `b9d.frozen_population` would NOT catch it, because it raises only when a
        curve is in the inventory and missing from the cohort. Its docstring says membership must
        agree "bidirectionally"; the code checks one direction. Pointing every consumer at the
        subsample makes the claim true rather than relying on the gap.
        """
        commands = W.stage_commands(pathlib.Path("/tmp/b11a-iso"))
        for stage in ("signature_inventory", "transaction_bodies", "decode_and_reserves",
                      "reserve_coverage_gate"):
            with self.subTest(stage=stage):
                joined = " ".join(commands[stage]["argv"])
                self.assertIn("b11a_subsample.sqlite", joined)
                self.assertNotIn("b11a_cohort.sqlite", joined)

    def test_only_the_subsample_stage_reads_the_full_cohort(self):
        """The frame is read exactly once, by the draw. Everything after sees the population."""
        commands = W.stage_commands(pathlib.Path("/tmp/b11a-iso"))
        readers = [name for name, command in commands.items()
                   if "b11a_cohort.sqlite" in " ".join(command["argv"])]
        self.assertEqual(sorted(readers), ["build_cohort", "subsample_cohort"])

    def test_b9d_run_now_names_both_fresh_sources(self):
        """The defect this handoff repaired: without them the run subcommand falls back to the
        burned module constants."""
        argv = W.stage_commands(pathlib.Path("/tmp/b11a-iso"))["transaction_bodies"]["argv"]
        self.assertIn("--b9c", argv)
        self.assertIn("--b9a", argv)
        for index, part in enumerate(argv):
            if part in ("--b9c", "--b9a"):
                with self.subTest(option=part):
                    self.assertTrue(argv[index + 1].startswith("/tmp/b11a-iso"))

    def test_the_local_adapter_stage_makes_no_network_call(self):
        commands = W.stage_commands()
        for name in W.LOCAL_STAGES:
            with self.subTest(stage=name):
                self.assertNotIn("--rpc-env", commands[name]["argv"])
                self.assertTrue(commands[name].get("local"))

    def test_an_unresolved_stage_quarantines_rather_than_running(self):
        """Every shipped stage is resolved now, so the refusal is driven with an injected
        unresolved command — the guard must still be there for the next stage that is not."""
        harness = Harness(self, [CUTOFF])
        commands = W.stage_commands(harness.directory)
        unresolved = dict(commands["transaction_bodies"], wiring="unresolved",
                          note="an injected unresolved stage")
        state = W.initial_state(W.verify_preregistration(), W.build_manifest(), 1)
        state["endpoint"] = W.endpoint_receipt(URL)
        with self.assertRaisesRegex(W.Quarantined, W.Q11_STAGE_WIRING_UNRESOLVED):
            W.run_stage("transaction_bodies", unresolved, state,
                        runner=harness.runner, log_dir=harness.paths["log_dir"],
                        receipt_dir=harness.paths["receipt_dir"],
                        state_path=harness.paths["state_path"])
        self.assertEqual(harness.ran, [])

    def test_every_resolved_stage_writes_only_into_the_b11a_directory(self):
        directory = pathlib.Path("/tmp/b11a-isolated")
        commands = W.stage_commands(directory)
        for name, command in commands.items():
            if command["wiring"] != "resolved":
                continue
            with self.subTest(stage=name):
                paths = [part for part in command["argv"]
                         if part.endswith((".sqlite", ".jsonl", ".json"))]
                self.assertTrue(paths, f"{name} names no artifact path")
                for path in paths:
                    self.assertTrue(path.startswith(str(directory)),
                                    f"{name} writes outside the B11a directory: {path}")

    def test_no_stage_argv_points_at_a_burned_artifact(self):
        for name, command in W.stage_commands().items():
            if command["wiring"] != "resolved":
                continue
            with self.subTest(stage=name):
                joined = " ".join(command["argv"])
                for burned in ("b9a_outcomes", "b9c_signature_inventory.sqlite",
                               "b9d_transaction_bodies.sqlite", "b10b_observed_paths"):
                    self.assertNotIn(burned, joined)


class SecretTests(unittest.TestCase):
    """A redaction that fails silently looks exactly like one that worked."""

    def setUp(self):
        self.previous = os.environ.get("B11C_TEST_API_KEY")
        os.environ["B11C_TEST_API_KEY"] = "SUPERSECRETVALUE123"
        self.addCleanup(self._restore)

    def _restore(self):
        if self.previous is None:
            os.environ.pop("B11C_TEST_API_KEY", None)
        else:
            os.environ["B11C_TEST_API_KEY"] = self.previous

    def test_the_endpoint_receipt_is_scheme_and_host_only(self):
        self.assertEqual(W.endpoint_receipt(URL), "https://rpc.invalid")
        self.assertNotIn("api-key", W.endpoint_receipt(URL))
        self.assertNotIn("SECRETVALUE", W.endpoint_receipt(URL))

    def test_the_real_endpoint_receipt_carries_no_query(self):
        url = os.environ.get(W.RPC_ENV_VAR)
        if url:
            receipt = W.endpoint_receipt(url)
            self.assertNotIn("?", receipt)
            self.assertNotIn("=", receipt)
            self.assertEqual(receipt.count("/"), 2)

    def test_a_secret_about_to_be_written_is_fatal(self):
        for payload in ("prefix SUPERSECRETVALUE123 suffix",
                        {"argv": ["--key", "SUPERSECRETVALUE123"]},
                        {"nested": {"deep": "SUPERSECRETVALUE123"}}):
            with self.subTest(payload=type(payload).__name__):
                with self.assertRaisesRegex(W.Quarantined, W.Q09_SECRET_WOULD_BE_WRITTEN):
                    W.assert_no_secret(payload, "test")

    def test_the_refusal_explains_why_nothing_is_redacted(self):
        try:
            W.assert_no_secret("SUPERSECRETVALUE123", "test")
        except W.Quarantined as error:
            self.assertIn("looks exactly like one that worked", str(error))

    def test_a_clean_payload_passes(self):
        self.assertTrue(W.assert_no_secret({"endpoint": "https://rpc.invalid"}, "test"))

    def test_a_state_write_carrying_a_secret_is_refused(self):
        """The scan lives in the atomic writer, so every durable file goes through it."""
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-secret-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        with self.assertRaisesRegex(W.Quarantined, W.Q09_SECRET_WOULD_BE_WRITTEN):
            W.atomic_write_json(directory / "state.json",
                                {"url": "https://x/?k=SUPERSECRETVALUE123"}, "test state")
        self.assertFalse((directory / "state.json").exists())

    def test_a_stage_argv_carrying_a_secret_is_refused_before_it_runs(self):
        harness = Harness(self, [CUTOFF])
        commands = harness.resolved_commands()
        leaking = dict(commands["program_boundary"])
        leaking["argv"] = list(leaking["argv"]) + ["--key", "SUPERSECRETVALUE123"]
        state = W.initial_state(W.verify_preregistration(), W.build_manifest(), 1)
        state["endpoint"] = W.endpoint_receipt(URL)
        with self.assertRaisesRegex(W.Quarantined, W.Q09_SECRET_WOULD_BE_WRITTEN):
            W.run_stage("program_boundary", leaking, state, runner=harness.runner,
                        log_dir=harness.paths["log_dir"],
                        receipt_dir=harness.paths["receipt_dir"],
                        state_path=harness.paths["state_path"])
        self.assertEqual(harness.ran, [])

    def test_state_and_receipts_carry_no_secret(self):
        harness = Harness(self, [CUTOFF])
        harness.watch_all(poll_seconds=1, max_iterations=1)
        text = harness.paths["state_path"].read_text()
        for receipt in sorted(harness.paths["receipt_dir"].glob("*.json")):
            text += receipt.read_text()
        self.assertNotIn("SECRETVALUE", text)
        self.assertNotIn("api-key", text)
        self.assertIn("https://rpc.invalid", text)

    def test_an_endpoint_without_a_host_is_refused(self):
        """Still refused; the wording now comes from the one shared sanitizer both modules use."""
        for bad in ("not-a-url", "https:///nohost", "ftp://host/x", "https://host:notaport/x"):
            with self.subTest(bad=bad):
                with self.assertRaises(W.WatcherRefused):
                    W.endpoint_receipt(bad)

    def test_the_endpoint_receipt_keeps_only_scheme_host_and_explicit_port(self):
        """The leak this replaces: a path credential survived a sanitizer that stripped queries."""
        for url, expected in (
                ("https://mainnet.helius-rpc.com/?api-key=SECRETVALUE1234567890",
                 "https://mainnet.helius-rpc.com"),
                ("https://solana-mainnet.core.chainstack.com/abcdef0123456789abcdef0123456789",
                 "https://solana-mainnet.core.chainstack.com"),
                ("https://user:pass@host.example/keymaterial123456",
                 "https://host.example"),
                ("https://[2001:db8::1]:8899/secretpath1234567", "https://[2001:db8::1]:8899"),
                ("http://127.0.0.1:8899", "http://127.0.0.1:8899"),
                ("https://host.example:443/x#fragment", "https://host.example:443")):
            with self.subTest(url=url):
                self.assertEqual(W.endpoint_receipt(url), expected)

    def test_the_watcher_and_b9d_agree_on_the_endpoint_identity(self):
        """Two sanitizers that disagreed is what let the credential through. There is now one."""
        B9D = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
        for url in ("https://solana-mainnet.core.chainstack.com/abcdef0123456789abcdef0123456789",
                    "https://mainnet.helius-rpc.com/?api-key=SECRETVALUE1234567890",
                    "https://[2001:db8::1]:8899/secretpath1234567"):
            with self.subTest(url=url):
                self.assertEqual(W.endpoint_receipt(url), B9D.endpoint_reference(url))


class CompositionTests(unittest.TestCase):
    """Counts describe the window, and descriptions are what burn it."""

    def test_a_count_in_a_status_payload_is_refused(self):
        for field in ("curves", "creates", "transactions", "population", "count"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(W.Quarantined, W.Q10_COMPOSITION_WOULD_LEAK):
                    W.assert_no_composition({field: 1234}, "status")

    def test_the_shipped_status_carries_no_count(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        view = W.status(harness.paths["state_path"], harness.paths["receipt_dir"])
        self.assertFalse(view["composition_published"])
        self.assertFalse(view["results_unlocked"])
        self.assertIn("slots_remaining", view)

    def test_the_status_publishes_stage_state_and_nothing_else(self):
        harness = Harness(self, [CUTOFF])
        harness.watch_all(poll_seconds=1, max_iterations=1)
        view = W.status(harness.paths["state_path"], harness.paths["receipt_dir"],
                        harness.directory / "supervisor.lock")
        # No process is running once the harness returns, so the live state is `dead` and the
        # stored value is published separately. That is the whole point of the split.
        self.assertEqual(view["liveness"], W.LIVENESS_DEAD)
        self.assertEqual(view["state"], W.LIVENESS_DEAD)
        self.assertEqual(view["reported_state"], W.STATE_ALL_STAGES_COMPLETE)
        self.assertEqual(sorted(view["stages_completed"]), sorted(W.RUN_ORDER))
        self.assertEqual(view["stages_remaining"], [])

    def test_a_state_write_carrying_a_count_is_refused(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        state = json.loads(harness.paths["state_path"].read_text())
        state["curves_enumerated"] = 1234
        with self.assertRaisesRegex(W.Quarantined, W.Q10_COMPOSITION_WOULD_LEAK):
            W.write_state(state, harness.paths["state_path"])

    def test_a_status_carrying_a_count_is_refused(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        state = json.loads(harness.paths["state_path"].read_text())
        state["transactions_collected"] = 99
        # Written past the guard, as a corrupted or hand-edited state file would be.
        harness.paths["state_path"].write_text(json.dumps(state))
        with self.assertRaisesRegex(W.Quarantined, W.Q10_COMPOSITION_WOULD_LEAK):
            W.status(harness.paths["state_path"], harness.paths["receipt_dir"])

    def test_a_stage_name_containing_a_composition_word_is_not_a_leak(self):
        """`enumerate_creates` is a name, not a count. A scan that fired on the pipeline's own
        vocabulary would be turned off within a week."""
        self.assertTrue(W.assert_no_composition(
            {"stage": "enumerate_creates", "stages_completed": ["enumerate_creates"]}, "status"))

    def test_the_dry_run_plan_publishes_no_composition(self):
        plan = W.dry_run_plan()
        self.assertFalse(plan["composition_published"])
        self.assertFalse(plan["results_unlocked"])


class RetryTests(unittest.TestCase):
    """Bounded retries for a hiccup, immediate quarantine for anything else."""

    def test_a_transport_hiccup_is_retried(self):
        attempts = {"n": 0}

        def flaky(url, method, params):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("connection reset by peer")
            return CUTOFF - 1

        self.assertEqual(W.poll_with_backoff(URL, transport=flaky, sleeper=lambda _s: None),
                         CUTOFF - 1)
        self.assertEqual(attempts["n"], 3)

    def test_retries_are_bounded(self):
        def always(url, method, params):
            raise RuntimeError("gateway timeout")

        with self.assertRaisesRegex(W.Quarantined, W.Q05_RETRIES_EXHAUSTED):
            W.poll_with_backoff(URL, transport=always, retries=3, sleeper=lambda _s: None)

    def test_a_non_retryable_failure_quarantines_immediately(self):
        attempts = {"n": 0}

        def fatal(url, method, params):
            attempts["n"] += 1
            raise RuntimeError("401 unauthorized")

        with self.assertRaisesRegex(W.Quarantined, W.Q06_NON_RETRYABLE_RPC):
            W.poll_with_backoff(URL, transport=fatal, sleeper=lambda _s: None)
        self.assertEqual(attempts["n"], 1)

    def test_the_classifier_distinguishes_the_two(self):
        for message, retryable in (("gateway timeout", True), ("429 too many requests", True),
                                   ("connection refused", True), ("503", True),
                                   ("401 unauthorized", False), ("invalid params", False),
                                   ("method not found", False)):
            with self.subTest(message=message):
                self.assertEqual(W.is_retryable(message), retryable)

    def test_the_backoff_grows_and_is_capped(self):
        slept = []

        def always(url, method, params):
            raise RuntimeError("timeout")

        with self.assertRaises(W.Quarantined):
            W.poll_with_backoff(URL, transport=always, retries=6, sleeper=slept.append)
        self.assertEqual(slept, sorted(slept))
        self.assertLessEqual(max(slept), W.BACKOFF_CAP_SECONDS)
        # One fewer sleep than attempts: the last backoff before giving up buys nothing, and
        # counting them is what makes the bound observable rather than merely stated.
        self.assertEqual(len(slept), 5)


class TransportClassificationTests(unittest.TestCase):
    """The failure that killed a run: a transient URLError whose TEXT matched no marker.

    Classification is by TYPE for transport faults now, so a name-resolution blip and a TLS error
    are retried like every other transport fault instead of quarantining a supervisor built to wait
    for days.
    """

    def url_error(self, reason):
        return urllib.error.URLError(reason)

    def http_error(self, status):
        return urllib.error.HTTPError(URL, status, "x", {}, io.BytesIO(b""))

    def test_a_dns_failure_is_retryable(self):
        """The regression. Its text contains no marker, and it used to be fatal."""
        error = self.url_error(OSError(-3, "Temporary failure in name resolution"))
        self.assertFalse(W.is_retryable(error), "still matches no marker, as before")
        self.assertTrue(W.is_retryable_failure(error), "but is now classified by type")

    def test_a_tls_failure_is_retryable(self):
        error = self.url_error(ssl.SSLError(1, "[SSL] record layer failure"))
        self.assertFalse(W.is_retryable(error))
        self.assertTrue(W.is_retryable_failure(error))

    def test_connection_faults_and_timeouts_are_retryable(self):
        for error in (self.url_error(ConnectionRefusedError(111, "Connection refused")),
                      self.url_error(ConnectionResetError(104, "Connection reset by peer")),
                      self.url_error("timed out"),
                      TimeoutError("timed out"),
                      OSError(101, "Network is unreachable")):
            with self.subTest(error=type(error).__name__):
                self.assertTrue(W.is_retryable_failure(error))

    def test_every_transient_http_status_is_retryable(self):
        for status in (408, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.assertTrue(W.is_retryable_failure(self.http_error(status)))

    def test_403_is_terminal_and_the_message_matcher_cannot_re_admit_it(self):
        """A 403 body could contain '503' or '429'; the type answer must be final."""
        self.assertFalse(W.is_retryable_failure(self.http_error(403)))
        poisoned = urllib.error.HTTPError(URL, 403, "429 503 gateway timeout", {}, io.BytesIO(b""))
        self.assertTrue(W.is_retryable(poisoned), "its text does match markers")
        self.assertFalse(W.is_retryable_failure(poisoned), "but 403 is still terminal")

    def test_other_http_statuses_are_terminal(self):
        for status in (400, 401, 404, 410, 422, 501):
            with self.subTest(status=status):
                self.assertFalse(W.is_retryable_failure(self.http_error(status)))

    def test_httperror_is_classified_before_its_urlerror_base(self):
        """HTTPError subclasses URLError. The wrong isinstance order retries every 403."""
        self.assertTrue(issubclass(urllib.error.HTTPError, urllib.error.URLError))
        self.assertFalse(W.is_retryable_failure(self.http_error(403)))

    def test_a_minus_32002_plan_refusal_is_terminal(self):
        """It arrives as an RPC error inside a successful response, not as a status."""
        error = B11A.WindowRefused(
            "RPC error: {'code': -32002, 'message': 'Archive, Debug and Trace requests are not "
            "available on your current plan'}")
        self.assertFalse(W.is_retryable_failure(error))

    def test_a_terminal_marker_beats_a_retryable_one_in_the_same_message(self):
        """What the terminal list is actually FOR, and the only case where it changes the answer.

        A -32002 message on its own matches no retryable marker either, so the guard would look
        redundant. It earns its place on precedence: a plan refusal whose text also happens to carry
        '503' or 'timeout' -- a provider quoting a status in prose, or an upstream detail appended --
        must still be terminal. Without the guard this message is retried six times against an
        answer that will never change.
        """
        both = B11A.WindowRefused(
            "RPC error: {'code': -32002, 'message': 'archive not available on your plan; "
            "upstream returned 503 gateway timeout'}")
        self.assertTrue(W.is_retryable(both), "its text does match retryable markers")
        self.assertFalse(W.is_retryable_failure(both), "but the terminal marker wins")

    def test_a_minus_32005_node_behind_is_still_retryable(self):
        """Preserved: the marker list is kept for exactly this, an RPC-level transient."""
        error = B11A.WindowRefused("RPC error: {'code': -32005, 'message': 'node is behind'}")
        self.assertTrue(W.is_retryable_failure(error))

    def test_a_genuine_rpc_mistake_is_still_terminal(self):
        for message in ("invalid params", "method not found", "401 unauthorized"):
            with self.subTest(message=message):
                self.assertFalse(W.is_retryable_failure(RuntimeError(message)))

    def test_the_success_path_is_unchanged(self):
        def healthy(url, method, params):
            return CUTOFF - 1

        self.assertEqual(W.poll_with_backoff(URL, transport=healthy, sleeper=lambda _s: None),
                         CUTOFF - 1)

    def test_a_dns_blip_now_recovers_instead_of_quarantining(self):
        """End to end: the exact shape that killed the run, survived."""
        attempts = {"n": 0}

        def blip(url, method, params):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise urllib.error.URLError(
                    OSError(-3, "Temporary failure in name resolution"))
            return CUTOFF - 1

        self.assertEqual(W.poll_with_backoff(URL, transport=blip, sleeper=lambda _s: None),
                         CUTOFF - 1)
        self.assertEqual(attempts["n"], 3)

    def test_the_bounds_are_unchanged(self):
        self.assertEqual(W.MAX_POLL_RETRIES, 6)
        self.assertEqual(W.BACKOFF_BASE_SECONDS, 5)
        self.assertEqual(W.BACKOFF_CAP_SECONDS, 120)
        slept = []

        def always(url, method, params):
            raise urllib.error.URLError(OSError(-3, "Temporary failure in name resolution"))

        with self.assertRaises(W.Quarantined):
            W.poll_with_backoff(URL, transport=always, retries=6, sleeper=slept.append)
        self.assertEqual(slept, [5, 10, 20, 40, 80])
        self.assertLessEqual(max(slept), W.BACKOFF_CAP_SECONDS)


class DurableQuarantineTests(unittest.TestCase):
    """A supervisor that dies must not leave a state file claiming it is healthy."""

    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        self.state_path = self.directory / "supervisor_state.json"
        self.state = {"schema_version": W.SCHEMA_VERSION, "state": W.STATE_WAITING,
                      "quarantine": None, "polls": 4, "stages_completed": [],
                      "stage_in_flight": None, "cutoff_slot_inclusive": CUTOFF,
                      "last_tip_slot": CUTOFF - 10, "last_poll_at": 0, "endpoint": None}

    def stored(self):
        return json.loads(self.state_path.read_text())

    def test_a_non_retryable_failure_is_persisted_before_the_raise(self):
        def fatal(url, method, params):
            raise urllib.error.HTTPError(URL, 403, "Forbidden", {}, io.BytesIO(b""))

        with self.assertRaisesRegex(W.Quarantined, W.Q06_NON_RETRYABLE_RPC):
            W.poll_with_backoff(URL, transport=fatal, sleeper=lambda _s: None,
                                state=self.state, state_path=self.state_path)
        stored = self.stored()
        self.assertEqual(stored["state"], W.STATE_QUARANTINED)
        self.assertEqual(stored["quarantine"]["reason_code"], W.Q06_NON_RETRYABLE_RPC)
        self.assertIn("403", stored["quarantine"]["diagnostic"])

    def test_exhaustion_is_persisted_too(self):
        def always(url, method, params):
            raise urllib.error.URLError(OSError(-3, "Temporary failure in name resolution"))

        with self.assertRaisesRegex(W.Quarantined, W.Q05_RETRIES_EXHAUSTED):
            W.poll_with_backoff(URL, transport=always, retries=2, sleeper=lambda _s: None,
                                state=self.state, state_path=self.state_path)
        stored = self.stored()
        self.assertEqual(stored["state"], W.STATE_QUARANTINED)
        self.assertEqual(stored["quarantine"]["reason_code"], W.Q05_RETRIES_EXHAUSTED)
        self.assertIn("name resolution", stored["quarantine"]["diagnostic"])

    def test_a_non_finalized_tip_is_persisted_too(self):
        """Q04 already named its reason; it just never reached the state file."""
        def wrong(url, method, params):
            return "not-a-slot"

        with self.assertRaisesRegex(W.Quarantined, W.Q04_NON_FINALIZED_SLOT):
            W.poll_with_backoff(URL, transport=wrong, sleeper=lambda _s: None,
                                state=self.state, state_path=self.state_path)
        self.assertEqual(self.stored()["quarantine"]["reason_code"], W.Q04_NON_FINALIZED_SLOT)

    def test_the_write_happens_before_the_raise_not_after(self):
        """Driven, not assumed: the file must already be on disk when the exception surfaces."""
        observed = {}

        def fatal(url, method, params):
            raise urllib.error.HTTPError(URL, 401, "x", {}, io.BytesIO(b""))

        try:
            W.poll_with_backoff(URL, transport=fatal, sleeper=lambda _s: None,
                                state=self.state, state_path=self.state_path)
        except W.Quarantined:
            observed["existed_at_raise_time"] = self.state_path.exists()
            observed["state_at_raise_time"] = self.stored()["state"]
        self.assertTrue(observed["existed_at_raise_time"])
        self.assertEqual(observed["state_at_raise_time"], W.STATE_QUARANTINED)

    def test_the_diagnostic_distinguishes_dns_from_tls_from_a_status(self):
        cases = {
            urllib.error.URLError(OSError(-3, "Temporary failure in name resolution")):
                "name resolution",
            urllib.error.URLError(ssl.SSLError(1, "[SSL] record layer failure")): "SSL",
            urllib.error.HTTPError(URL, 503, "x", {}, io.BytesIO(b"")): "HTTP 503",
        }
        for error, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, W.poll_failure_diagnostic(error))

    def test_the_diagnostic_carries_no_endpoint_or_credential(self):
        """An HTTPError holds the full URL in `.url`, and this endpoint's key is in its PATH."""
        secret = "sEcReTkEy0123456789abcdef"
        error = urllib.error.HTTPError(f"https://host.invalid/{secret}", 403, "Forbidden", {},
                                       io.BytesIO(b""))
        diagnostic = W.poll_failure_diagnostic(error)
        self.assertNotIn(secret, diagnostic)
        self.assertNotIn("host.invalid", diagnostic)
        self.assertEqual(diagnostic, "HTTPError HTTP 403")

    def test_a_diagnostic_carrying_the_live_secret_refuses_to_be_written(self):
        """The project's stance: refuse the write, never redact it silently.

        The secret is INJECTED rather than taken from the ambient environment. Reading
        `_secret_values()` made this test skip whenever the suite ran without the credential
        exported, which is most of the time -- and a guard that skips is a guard a mutant walks
        straight through. It did: removing the `assert_no_secret` call survived a mutation run.
        """
        original = W._secret_values
        W._secret_values = lambda: {"sEcReTkEy0123456789abcdef"}
        self.addCleanup(lambda: setattr(W, "_secret_values", original))
        leaked = "URLError: OSError: connect to https://host/sEcReTkEy0123456789abcdef failed"
        with self.assertRaisesRegex(W.Quarantined, W.Q09_SECRET_WOULD_BE_WRITTEN):
            W.record_quarantine(self.state, self.state_path, W.Q06_NON_RETRYABLE_RPC, leaked)
        self.assertFalse(self.state_path.exists(),
                         "nothing may be written when the diagnostic is refused")

    def test_a_clean_diagnostic_still_writes_with_the_guard_armed(self):
        """The other half: the guard must not refuse an honest diagnostic."""
        original = W._secret_values
        W._secret_values = lambda: {"sEcReTkEy0123456789abcdef"}
        self.addCleanup(lambda: setattr(W, "_secret_values", original))
        W.record_quarantine(self.state, self.state_path, W.Q06_NON_RETRYABLE_RPC,
                            "URLError: OSError: Temporary failure in name resolution")
        self.assertEqual(self.stored()["quarantine"]["reason_code"], W.Q06_NON_RETRYABLE_RPC)

    def test_status_reports_the_persisted_quarantine_rather_than_healthy_waiting(self):
        def fatal(url, method, params):
            raise urllib.error.HTTPError(URL, 403, "Forbidden", {}, io.BytesIO(b""))

        with self.assertRaises(W.Quarantined):
            W.poll_with_backoff(URL, transport=fatal, sleeper=lambda _s: None,
                                state=self.state, state_path=self.state_path)
        view = W.status(state_path=self.state_path, receipt_dir=self.directory / "receipts",
                        lock_path=self.directory / "supervisor.lock")
        self.assertEqual(view["reported_state"], W.STATE_QUARANTINED)
        self.assertEqual(view["quarantine"]["reason_code"], W.Q06_NON_RETRYABLE_RPC)
        self.assertNotEqual(view["reported_state"], W.STATE_WAITING)

    def test_a_dead_process_after_a_crash_no_longer_reads_as_waiting(self):
        """The exact operator-facing lie this fixes, reproduced end to end."""
        before = W.status(state_path=self.state_path, receipt_dir=self.directory / "receipts",
                          lock_path=self.directory / "supervisor.lock")
        self.assertEqual(before["state"], W.LIVENESS_NOT_STARTED)
        W.write_state(self.state, self.state_path)
        healthy_looking = W.status(state_path=self.state_path,
                                   receipt_dir=self.directory / "receipts",
                                   lock_path=self.directory / "supervisor.lock")
        self.assertEqual(healthy_looking["reported_state"], W.STATE_WAITING)
        self.assertIsNone(healthy_looking["quarantine"])
        W.record_quarantine(self.state, self.state_path, W.Q06_NON_RETRYABLE_RPC,
                            "URLError: OSError: Temporary failure in name resolution")
        after = W.status(state_path=self.state_path, receipt_dir=self.directory / "receipts",
                         lock_path=self.directory / "supervisor.lock")
        self.assertEqual(after["reported_state"], W.STATE_QUARANTINED)
        self.assertIn("name resolution", after["quarantine"]["diagnostic"])

    def test_no_state_means_no_write_and_no_crash(self):
        """Driven in isolation without a state file must still classify and raise."""
        def fatal(url, method, params):
            raise urllib.error.HTTPError(URL, 403, "x", {}, io.BytesIO(b""))

        with self.assertRaisesRegex(W.Quarantined, W.Q06_NON_RETRYABLE_RPC):
            W.poll_with_backoff(URL, transport=fatal, sleeper=lambda _s: None)
        self.assertFalse(self.state_path.exists())


class IncidentQuarantineTests(unittest.TestCase):
    """Retiring a run whose evidence must NOT be reused, without deleting the record of it."""

    SECRET = "abcdef0123456789abcdef0123456789"

    def setUp(self):
        self.work = pathlib.Path(tempfile.mkdtemp(prefix="b11c-inc-"))
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        (self.work / "receipts").mkdir()
        (self.work / "logs").mkdir()
        self.tainted = self.work / "b11a_program_boundary.json"
        self.tainted.write_bytes(
            b"SQLite format 3\x00boundary_endpoint_referencehttps://host.example/"
            + self.SECRET.encode())
        self.clean_partial = self.work / "b11a_creates.sqlite"
        self.clean_partial.write_bytes(b"SQLite format 3\x00partial scan, no credential")
        (self.work / "receipts" / "program_boundary.json").write_text(
            json.dumps({"stage": "program_boundary", "completed": True}))
        (self.work / "logs" / "program_boundary.stdout.log").write_text("boundary ok\n")
        self.state_path = self.work / "supervisor_state.json"
        self.state_path.write_text(json.dumps({"state": W.STATE_RUNNING_STAGE,
                                               "stages_completed": ["program_boundary"]}))
        (self.work / "supervisor.lock").write_text("4242")

    def quarantine(self, **kwargs):
        return W.incident_quarantine(
            "Q_CREDENTIAL_IN_ARTIFACT", "a persisted endpoint carried a path credential",
            secret_bearing=[self.tainted], work_dir=self.work, state_path=self.state_path,
            lock_path=self.work / "supervisor.lock", receipt_dir=self.work / "receipts",
            log_dir=self.work / "logs", incident_dir=self.work / "incidents",
            stamp="20260804T200000Z", secret_values={self.SECRET}, **kwargs)

    def report(self):
        return json.loads((self.work / "incidents" / "20260804T200000Z" /
                           W.INCIDENT_MARKER).read_text())

    def test_the_credential_bearing_artifact_is_removed(self):
        self.quarantine()
        self.assertFalse(self.tainted.exists(), "a credential-bearing artifact may not be retained")

    def test_its_forensics_are_captured_before_removal(self):
        expected = hashlib.sha256(self.tainted.read_bytes()).hexdigest()
        size = self.tainted.stat().st_size
        report = self.quarantine()
        removed = {r["path"]: r for r in report["removed_because_credential_bearing"]}
        self.assertIn("b11a_program_boundary.json", removed)
        self.assertEqual(removed["b11a_program_boundary.json"]["sha256"], expected)
        self.assertEqual(removed["b11a_program_boundary.json"]["size_bytes"], size)
        self.assertTrue(removed["b11a_program_boundary.json"]["credential_present"])

    def test_the_report_never_records_the_endpoint_value_or_the_credential(self):
        self.quarantine()
        text = json.dumps(self.report())
        self.assertNotIn(self.SECRET, text)
        self.assertNotIn("host.example", text)

    def test_the_report_refuses_to_be_written_if_it_would_carry_a_secret(self):
        """The stance everywhere here: refuse the write, never redact."""
        with self.assertRaisesRegex(W.Quarantined, W.Q09_SECRET_WOULD_BE_WRITTEN):
            W.incident_quarantine(
                "Q_TEST", f"leaky reason containing {self.SECRET}",
                secret_bearing=[self.tainted], work_dir=self.work, state_path=self.state_path,
                lock_path=self.work / "supervisor.lock", receipt_dir=self.work / "receipts",
                log_dir=self.work / "logs", incident_dir=self.work / "incidents",
                stamp="20260804T210000Z", secret_values={self.SECRET})

    def test_credential_free_evidence_is_preserved_not_erased(self):
        report = self.quarantine()
        preserved = {r["path"] for r in report["preserved_credential_free"]}
        self.assertIn("receipts/program_boundary.json", preserved)
        self.assertIn("logs/program_boundary.stdout.log", preserved)
        self.assertIn("supervisor_state.json", preserved)
        self.assertIn("b11a_creates.sqlite", preserved)
        moved = self.work / "incidents" / "20260804T200000Z"
        self.assertTrue((moved / "receipts" / "program_boundary.json").exists())
        self.assertTrue((moved / "b11a_creates.sqlite").exists())

    def test_a_credential_bearing_file_is_removed_even_if_not_named(self):
        """Named OR detected. A caller who forgets one must not thereby retain it."""
        sneaky = self.work / "logs" / "extra.log"
        sneaky.write_text(f"endpoint https://host.example/{self.SECRET}\\n")
        report = self.quarantine()
        self.assertFalse(sneaky.exists())
        self.assertIn("logs/extra.log",
                      {r["path"] for r in report["removed_because_credential_bearing"]})

    def test_the_clean_run_starts_from_zero_receipts(self):
        self.quarantine()
        self.assertEqual(W.completed_stages(self.work / "receipts"), [],
                         "a rerun must regenerate every stage, not resume")
        self.assertFalse(self.state_path.exists())
        self.assertFalse((self.work / "supervisor.lock").exists())

    def test_the_incident_is_marked_not_for_resume_and_kept_out_of_superseded(self):
        self.quarantine()
        report = self.report()
        self.assertEqual(report["reason_code"], "Q_CREDENTIAL_IN_ARTIFACT")
        self.assertIn("INVALIDATED", report["not_for_resume"])
        self.assertIn("zero receipts", report["not_for_resume"])
        self.assertTrue((self.work / "incidents" / "20260804T200000Z" /
                         "INVALIDATED_DO_NOT_RESUME.json").exists())
        self.assertFalse((self.work / "superseded").exists(),
                         "an incident must not appear where archived resumable runs live")

    def test_it_does_not_reuse_archive_run_which_rightly_refuses_a_receipted_run(self):
        """The reason this procedure exists at all."""
        with self.assertRaisesRegex(W.WatcherRefused, "completed stages"):
            W.archive_run("would be wrong", work_dir=self.work, state_path=self.state_path,
                          lock_path=self.work / "supervisor.lock",
                          archive_dir=self.work / "superseded")

    def test_every_examined_file_is_accounted_for(self):
        report = self.quarantine()
        self.assertEqual(report["files_examined"],
                         len(report["removed_because_credential_bearing"])
                         + len(report["preserved_credential_free"]))


class HeartbeatDuringAStageTests(unittest.TestCase):
    """A healthy 40-hour stage must not read as `stale`, and a hung one must not read as healthy.

    The poll clock stops when a stage starts, so judging a running stage by `last_poll_at` reported
    stale for the whole of a healthy stage AND masked `running_stage` in the operator's view -- the
    signal was useless exactly while collection was happening. Two clocks now: one says the
    SUPERVISOR is alive, the other says the STAGE is producing.
    """

    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-hb-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.state_path = self.directory / "state.json"
        self.lock_path = self.directory / "supervisor.lock"

    def running_state(self, heartbeat_age=0, progress_age=0, now=None):
        now = int(time.time()) if now is None else now
        return {"schema_version": W.SCHEMA_VERSION, "state": W.STATE_RUNNING_STAGE,
                "quarantine": None, "polls": 38, "stages_completed": ["program_boundary"],
                "stage_in_flight": "enumerate_creates", "stage_pid": 4242,
                "stage_heartbeat_at": now - heartbeat_age,
                "stage_progress_at": now - progress_age,
                "stage_output_bytes": 2216,
                "cutoff_slot_inclusive": CUTOFF, "last_tip_slot": CUTOFF,
                # Deliberately ancient: this is the clock that used to be consulted.
                "last_poll_at": now - 100_000, "poll_seconds": 300, "endpoint": None}

    def test_a_long_healthy_stage_is_alive_not_stale(self):
        state = self.running_state(heartbeat_age=5, progress_age=5)
        signals = W.liveness(state, lock_path=self.lock_path)
        self.assertEqual(signals["heartbeat_source"], "stage")
        self.assertTrue(signals["heartbeat_fresh"])
        self.assertEqual(signals["heartbeat_age_seconds"], 5)

    def test_the_ancient_poll_clock_is_not_consulted_during_a_stage(self):
        """The whole defect in one assertion: last_poll_at is 100,000s old and irrelevant."""
        state = self.running_state(heartbeat_age=1)
        signals = W.liveness(state, lock_path=self.lock_path)
        self.assertLess(signals["heartbeat_age_seconds"], 100)
        self.assertEqual(signals["heartbeat_tolerance_seconds"],
                         W.STAGE_HEARTBEAT_SECONDS * W.HEARTBEAT_TOLERANCE_INTERVALS)

    def test_the_poll_clock_is_still_used_while_waiting_for_maturity(self):
        state = self.running_state(heartbeat_age=1)
        state["state"] = W.STATE_WAITING
        signals = W.liveness(state, lock_path=self.lock_path)
        self.assertEqual(signals["heartbeat_source"], "poll")
        self.assertFalse(signals["heartbeat_fresh"], "the poll clock is 100,000s old")

    def test_a_supervisor_that_stopped_heartbeating_mid_stage_is_not_alive(self):
        state = self.running_state(heartbeat_age=10_000)
        signals = W.liveness(state, lock_path=self.lock_path)
        self.assertFalse(signals["heartbeat_fresh"])

    def test_a_stalled_child_is_visible_behind_a_healthy_supervisor(self):
        """The failure mode the second clock exists for."""
        state = self.running_state(heartbeat_age=2, progress_age=10_000)
        signals = W.liveness(state, lock_path=self.lock_path)
        self.assertTrue(signals["heartbeat_fresh"], "the supervisor is fine")
        self.assertFalse(signals["stage_progressing"], "the stage is not")
        self.assertGreater(signals["stage_progress_age_seconds"], 900)
        self.assertEqual(signals["stage_pid"], 4242)

    def test_a_progressing_child_reports_progressing(self):
        state = self.running_state(heartbeat_age=2, progress_age=2)
        signals = W.liveness(state, lock_path=self.lock_path)
        self.assertTrue(signals["stage_progressing"])

    def test_progress_fields_are_absent_when_no_stage_is_running(self):
        state = self.running_state()
        state["state"] = W.STATE_WAITING
        signals = W.liveness(state, lock_path=self.lock_path)
        self.assertNotIn("stage_progressing", signals)

    def test_a_dead_parent_is_dead_however_fresh_the_stored_heartbeat_is(self):
        state = self.running_state(heartbeat_age=0, progress_age=0)
        W.write_state(state, self.state_path)
        view = W.status(state_path=self.state_path, receipt_dir=self.directory / "receipts",
                        lock_path=self.lock_path)
        self.assertFalse(view["pid_alive"])
        self.assertFalse(view["lock_held"])
        self.assertEqual(view["liveness"], W.LIVENESS_DEAD)
        self.assertEqual(view["state"], W.LIVENESS_DEAD, "a dead run must not present as running")
        self.assertEqual(view["reported_state"], W.STATE_RUNNING_STAGE)

    def test_a_missing_state_file_is_not_started_not_healthy(self):
        view = W.status(state_path=self.directory / "absent.json",
                        receipt_dir=self.directory / "receipts", lock_path=self.lock_path)
        self.assertEqual(view["liveness"], W.LIVENESS_NOT_STARTED)

    def test_the_operator_view_shows_running_stage_when_the_stage_heartbeat_is_fresh(self):
        """Requires a live-looking pid and lock, so the whole signal set agrees."""
        state = self.running_state(heartbeat_age=1, progress_age=1)
        W.write_state(state, self.state_path)
        self.lock_path.write_text(str(os.getpid()))
        original_process = W.process_is_this_watcher
        original_lock = W.lock_is_held
        W.process_is_this_watcher = lambda pid: True
        W.lock_is_held = lambda path=None: True
        self.addCleanup(lambda: setattr(W, "process_is_this_watcher", original_process))
        self.addCleanup(lambda: setattr(W, "lock_is_held", original_lock))
        view = W.status(state_path=self.state_path, receipt_dir=self.directory / "receipts",
                        lock_path=self.lock_path)
        self.assertEqual(view["liveness"], W.LIVENESS_ALIVE)
        self.assertEqual(view["state"], W.STATE_RUNNING_STAGE,
                         "running_stage must not be masked by an aged RPC poll")
        self.assertNotEqual(view["state"], W.LIVENESS_STALE)

    def test_the_heartbeat_helper_advances_the_supervisor_clock_every_call(self):
        state = self.running_state(heartbeat_age=50, progress_age=50)
        first = W.touch_stage_heartbeat(state, self.state_path, now=1000)
        second = W.touch_stage_heartbeat(state, self.state_path, now=1030)
        self.assertEqual((first, second), (1000, 1030))
        self.assertEqual(json.loads(self.state_path.read_text())["stage_heartbeat_at"], 1030)

    def test_progress_advances_only_when_the_stage_output_actually_grew(self):
        log = self.directory / "stage.stdout.log"
        log.write_text("first\n")
        state = self.running_state()
        state["stage_output_bytes"] = None
        W.touch_stage_heartbeat(state, self.state_path, stdout_path=log, now=1000)
        self.assertEqual(state["stage_progress_at"], 1000)
        # No new output: the supervisor clock moves, the progress clock does not.
        W.touch_stage_heartbeat(state, self.state_path, stdout_path=log, now=1030)
        self.assertEqual(state["stage_heartbeat_at"], 1030)
        self.assertEqual(state["stage_progress_at"], 1000)
        log.write_text("first\nsecond\n")
        W.touch_stage_heartbeat(state, self.state_path, stdout_path=log, now=1060)
        self.assertEqual(state["stage_progress_at"], 1060)

    def test_a_real_subprocess_stage_is_heartbeaten_while_it_runs(self):
        """End to end with a real child: the supervisor must tick more than once while waiting."""
        harness = Harness(self, [CUTOFF])
        state = {"schema_version": W.SCHEMA_VERSION, "state": W.STATE_WAITING, "quarantine": None,
                 "polls": 1, "stages_completed": [], "stage_in_flight": None, "stage_pid": None,
                 "stage_heartbeat_at": None, "stage_progress_at": None, "stage_output_bytes": None,
                 "cutoff_slot_inclusive": CUTOFF, "last_tip_slot": CUTOFF, "last_poll_at": 0,
                 "endpoint": None, "manifest_sha256": "0" * 64}
        stage = W.RUN_ORDER[0]
        command = {"argv": [sys.executable, "-c",
                            "import time,sys\n"
                            "for i in range(3):\n"
                            "    print(i, flush=True)\n"
                            "    time.sleep(0.2)\n"],
                   "wiring": "resolved", "note": "synthetic"}
        beats = []
        original = W.touch_stage_heartbeat

        def counting(state_arg, state_path, **kwargs):
            beats.append(kwargs.get("now"))
            return original(state_arg, state_path, **kwargs)

        W.touch_stage_heartbeat = counting
        self.addCleanup(lambda: setattr(W, "touch_stage_heartbeat", original))
        receipt = W.run_stage(stage, command, state, log_dir=harness.paths["log_dir"],
                             receipt_dir=harness.paths["receipt_dir"],
                             state_path=harness.paths["state_path"], heartbeat_seconds=0.1)
        self.assertTrue(receipt["completed"])
        self.assertEqual(receipt["exit_code"], 0)
        self.assertGreaterEqual(len(beats), 3, "the supervisor must tick while waiting, not once")
        self.assertIsNone(state["stage_pid"], "the child pid is cleared when the stage ends")
        self.assertGreater(state["stage_output_bytes"], 0)

    def test_the_child_pid_is_recorded_while_the_stage_runs(self):
        harness = Harness(self, [CUTOFF])
        state = {"schema_version": W.SCHEMA_VERSION, "state": W.STATE_WAITING, "quarantine": None,
                 "polls": 1, "stages_completed": [], "stage_in_flight": None, "stage_pid": None,
                 "stage_heartbeat_at": None, "stage_progress_at": None, "stage_output_bytes": None,
                 "cutoff_slot_inclusive": CUTOFF, "last_tip_slot": CUTOFF, "last_poll_at": 0,
                 "endpoint": None, "manifest_sha256": "0" * 64}
        command = {"argv": [sys.executable, "-c", "import time; time.sleep(0.4)"],
                   "wiring": "resolved", "note": "synthetic"}
        seen = {}
        original = W.touch_stage_heartbeat

        def capture(state_arg, state_path, **kwargs):
            result = original(state_arg, state_path, **kwargs)
            # Read AFTER the write this call performs: reading first would see the previous version
            # and assert that the very write under test had not happened yet.
            if state_arg.get("stage_pid") and "pid" not in seen:
                seen["pid"] = state_arg["stage_pid"]
                seen["on_disk"] = json.loads(pathlib.Path(state_path).read_text()).get("stage_pid")
            return result

        W.touch_stage_heartbeat = capture
        self.addCleanup(lambda: setattr(W, "touch_stage_heartbeat", original))
        W.run_stage(W.RUN_ORDER[0], command, state, log_dir=harness.paths["log_dir"],
                    receipt_dir=harness.paths["receipt_dir"],
                    state_path=harness.paths["state_path"], heartbeat_seconds=0.1)
        self.assertGreater(seen["pid"], 0)
        self.assertEqual(seen["on_disk"], seen["pid"], "the child pid must be durable, not in RAM")


class StateIsDurableAtEverySafetyBoundaryTests(unittest.TestCase):
    """The state file must be on disk BEFORE the thing it describes can go wrong.

    Three writes carried the whole resume story and none of them was pinned: deleting any one of
    them left the suite green. Each test below crashes the process at the boundary that write
    protects and reads the file back the way an operator would, so a deletion is caught by the
    consequence rather than by the line's presence.
    """

    class Boom(RuntimeError):
        """An injected crash, distinguishable from any refusal the watcher raises itself."""

    def stored(self, harness):
        return json.loads(harness.paths["state_path"].read_text())

    # -- boundary A: VERIFYING, before any resume or probe work ---------------------------------

    def test_verifying_is_on_disk_before_resume_work_begins(self):
        """If the run dies deciding whether a resume is safe, the file must say VERIFYING.

        Without this write the file still claims whatever the previous run left -- for a fresh run
        `initialising`, for a resumed one `waiting_for_maturity` -- and an operator reading it would
        believe the supervisor never got as far as checking.
        """
        harness = Harness(self, [CUTOFF - 1])
        original = W.assert_resume_is_safe
        self.addCleanup(lambda: setattr(W, "assert_resume_is_safe", original))
        seen = {}

        def crash(state, receipt_dir):
            seen["on_disk"] = json.loads(harness.paths["state_path"].read_text())
            raise self.Boom("killed while deciding whether the resume was safe")

        W.assert_resume_is_safe = crash
        with self.assertRaises(self.Boom):
            harness.watch(poll_seconds=1, max_iterations=1)
        self.assertEqual(seen["on_disk"]["state"], W.STATE_VERIFYING)
        self.assertEqual(self.stored(harness)["state"], W.STATE_VERIFYING)

    def test_the_endpoint_receipt_is_durable_at_the_same_boundary(self):
        """It is written in the same breath as VERIFYING, and it is what an operator checks."""
        harness = Harness(self, [CUTOFF - 1])
        original = W.assert_resume_is_safe
        self.addCleanup(lambda: setattr(W, "assert_resume_is_safe", original))
        W.assert_resume_is_safe = lambda *_a: (_ for _ in ()).throw(self.Boom("x"))
        with self.assertRaises(self.Boom):
            harness.watch(poll_seconds=1, max_iterations=1)
        stored = self.stored(harness)
        self.assertEqual(stored["endpoint"], W.endpoint_receipt(URL))
        self.assertNotIn("SECRETVALUE1234567890", json.dumps(stored))

    # -- boundary B: RUNNING_STAGE and stage_in_flight, before the subprocess ------------------

    def test_running_stage_and_stage_in_flight_are_on_disk_before_the_subprocess_starts(self):
        harness = Harness(self, [CUTOFF])
        seen = {}

        def runner(argv, stdout_path, stderr_path):
            # The FIRST call only: `seen` overwritten each stage would assert about the last one.
            seen.setdefault("on_disk", json.loads(harness.paths["state_path"].read_text()))
            seen.setdefault("stage_count", len(seen))
            pathlib.Path(stdout_path).write_text("")
            pathlib.Path(stderr_path).write_text("")
            return 0

        harness.runner = runner
        harness.watch(poll_seconds=1, max_iterations=1)
        self.assertEqual(seen["on_disk"]["state"], W.STATE_RUNNING_STAGE)
        self.assertEqual(seen["on_disk"]["stage_in_flight"], W.RUN_ORDER[0])

    def test_run_stage_records_running_stage_whatever_its_caller_left_behind(self):
        """`run_stage`'s own contract, not the loop's.

        `watch` happens to set RUNNING_STAGE before entering the stage loop, which made the
        assignment inside `run_stage` look redundant -- a mutation sweep survived deleting it. It is
        only redundant while the one existing caller keeps doing that. Driven directly here, so the
        function's own guarantee is pinned rather than inherited from its caller.
        """
        harness = Harness(self, [CUTOFF])
        state = {"schema_version": W.SCHEMA_VERSION, "state": W.STATE_WAITING,
                 "quarantine": None, "polls": 1, "stages_completed": [], "stage_in_flight": None,
                 "cutoff_slot_inclusive": CUTOFF, "last_tip_slot": CUTOFF, "last_poll_at": 0,
                 "endpoint": W.endpoint_receipt(URL), "manifest_sha256": "0" * 64}
        stage = W.RUN_ORDER[0]
        seen = {}

        def runner(argv, stdout_path, stderr_path):
            seen["on_disk"] = json.loads(harness.paths["state_path"].read_text())
            pathlib.Path(stdout_path).write_text("")
            pathlib.Path(stderr_path).write_text("")
            return 0

        W.run_stage(stage, harness.resolved_commands()[stage], state, runner=runner,
                    log_dir=harness.paths["log_dir"], receipt_dir=harness.paths["receipt_dir"],
                    state_path=harness.paths["state_path"])
        self.assertEqual(seen["on_disk"]["state"], W.STATE_RUNNING_STAGE,
                         "run_stage must record RUNNING_STAGE itself, not rely on its caller")
        self.assertEqual(seen["on_disk"]["stage_in_flight"], stage)

    def test_a_process_killed_mid_stage_cannot_leave_state_claiming_it_was_waiting(self):
        """The lie this write exists to prevent: a stage ran, the file says nothing happened."""
        harness = Harness(self, [CUTOFF])

        def crashing_runner(argv, stdout_path, stderr_path):
            pathlib.Path(stdout_path).write_text("partial\n")
            pathlib.Path(stderr_path).write_text("")
            raise self.Boom("SIGKILL during the stage")

        harness.runner = crashing_runner
        with self.assertRaises(self.Boom):
            harness.watch(poll_seconds=1, max_iterations=1)
        stored = self.stored(harness)
        self.assertNotEqual(stored["state"], W.STATE_WAITING)
        self.assertEqual(stored["state"], W.STATE_RUNNING_STAGE)
        self.assertEqual(stored["stage_in_flight"], W.RUN_ORDER[0])

    def test_resuming_from_that_crash_quarantines_rather_than_resuming(self):
        """A partial artifact is not a checkpoint, and the durable write is what makes it visible."""
        harness = Harness(self, [CUTOFF])

        def crashing_runner(argv, stdout_path, stderr_path):
            pathlib.Path(stdout_path).write_text("partial\n")
            pathlib.Path(stderr_path).write_text("")
            raise self.Boom("SIGKILL during the stage")

        harness.runner = crashing_runner
        with self.assertRaises(self.Boom):
            harness.watch(poll_seconds=1, max_iterations=1)
        with self.assertRaisesRegex(W.Quarantined, W.Q08_STAGE_INTERRUPTED):
            Harness(self, [CUTOFF]).watch(poll_seconds=1, max_iterations=1,
                                          **{k: v for k, v in harness.paths.items()})

    def test_no_receipt_is_written_for_a_stage_that_never_finished(self):
        harness = Harness(self, [CUTOFF])

        def crashing_runner(argv, stdout_path, stderr_path):
            pathlib.Path(stdout_path).write_text("")
            pathlib.Path(stderr_path).write_text("")
            raise self.Boom("killed")

        harness.runner = crashing_runner
        with self.assertRaises(self.Boom):
            harness.watch(poll_seconds=1, max_iterations=1)
        self.assertEqual(W.completed_stages(harness.paths["receipt_dir"]), [])

    # -- boundary C: the receipt, then stages_completed ----------------------------------------

    def test_stages_completed_is_durable_after_a_stage_succeeds(self):
        harness = Harness(self, [CUTOFF])
        harness.watch(poll_seconds=1, max_iterations=1)
        stored = self.stored(harness)
        self.assertEqual(stored["stages_completed"], list(W.RUN_ORDER))
        self.assertIsNone(stored["stage_in_flight"])

    def test_the_receipt_is_written_before_state_claims_the_stage_is_done(self):
        """Ordering, not just presence. The receipt is the authority; state derives from it.

        Crash immediately after the FIRST stage's receipt lands. The receipt must exist, and the
        durable state must not be claiming a later stage or completion.
        """
        harness = Harness(self, [CUTOFF])
        first = W.RUN_ORDER[0]
        observed = {}

        def runner(argv, stdout_path, stderr_path):
            pathlib.Path(stdout_path).write_text("")
            pathlib.Path(stderr_path).write_text("")
            if harness.ran and len(harness.ran) >= 1:
                observed["receipt_existed"] = W.receipt_path(
                    first, harness.paths["receipt_dir"]).exists()
                observed["state_when_second_started"] = json.loads(
                    harness.paths["state_path"].read_text())
                raise self.Boom("killed just after the first receipt")
            harness.ran.append(argv)
            return 0

        harness.runner = runner
        with self.assertRaises(self.Boom):
            harness.watch(poll_seconds=1, max_iterations=1)
        self.assertTrue(observed["receipt_existed"],
                        "the receipt must be durable before the next stage begins")
        self.assertEqual(observed["state_when_second_started"]["stages_completed"], [first],
                         "state must already record the finished stage, from its receipt")

    def test_a_receipted_stage_is_never_rerun(self):
        harness = Harness(self, [CUTOFF])
        harness.watch(poll_seconds=1, max_iterations=1)
        first_run = list(harness.ran)
        second = Harness(self, [CUTOFF])
        second.watch(poll_seconds=1, max_iterations=1,
                     **{k: v for k, v in harness.paths.items()})
        self.assertEqual(second.ran, [], "every stage already had a receipt; none may run again")
        self.assertEqual(len(first_run), len(W.RUN_ORDER))

    def test_completion_cannot_be_claimed_without_receipts(self):
        """`stages_completed` is derived from receipts, so deleting one un-completes the stage."""
        harness = Harness(self, [CUTOFF])
        harness.watch(poll_seconds=1, max_iterations=1)
        self.assertEqual(len(W.completed_stages(harness.paths["receipt_dir"])), len(W.RUN_ORDER))
        W.receipt_path(W.RUN_ORDER[-1], harness.paths["receipt_dir"]).unlink()
        remaining = W.completed_stages(harness.paths["receipt_dir"])
        self.assertNotIn(W.RUN_ORDER[-1], remaining)
        view = W.status(state_path=harness.paths["state_path"],
                        receipt_dir=harness.paths["receipt_dir"],
                        lock_path=harness.directory / "supervisor.lock")
        self.assertNotIn(W.RUN_ORDER[-1], view["stages_completed"])
        self.assertIn(W.RUN_ORDER[-1], view["stages_remaining"])

    def test_a_receipt_marked_incomplete_does_not_count_as_completed(self):
        harness = Harness(self, [CUTOFF])
        harness.watch(poll_seconds=1, max_iterations=1)
        path = W.receipt_path(W.RUN_ORDER[0], harness.paths["receipt_dir"])
        receipt = json.loads(path.read_text())
        receipt["completed"] = False
        path.write_text(json.dumps(receipt))
        self.assertNotIn(W.RUN_ORDER[0], W.completed_stages(harness.paths["receipt_dir"]))

    def test_receipts_that_are_not_a_prefix_of_the_run_order_quarantine(self):
        """A contradiction between receipts and the frozen order stops the run.

        This is the reachable half of the resume contradiction check: a receipt for the LAST stage
        with none before it is in run order and is not a PREFIX of it, which means every earlier
        stage was skipped.
        """
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        harness.paths["receipt_dir"].mkdir(parents=True, exist_ok=True)
        W.atomic_write_json(W.receipt_path(W.RUN_ORDER[-1], harness.paths["receipt_dir"]),
                            {"stage": W.RUN_ORDER[-1], "completed": True}, "out-of-order receipt")
        state = json.loads(harness.paths["state_path"].read_text())
        with self.assertRaisesRegex(W.Quarantined, W.Q12_DUPLICATE_STAGE):
            W.assert_resume_is_safe(state, harness.paths["receipt_dir"])

    def test_a_receipt_outside_the_run_order_is_invisible_by_construction(self):
        """Recorded rather than asserted-around: the unknown-stage branch cannot fire.

        `completed_stages` builds its list by iterating RUN_ORDER, so every element is a member of
        RUN_ORDER by construction and `assert_resume_is_safe`'s `stage not in RUN_ORDER` check is
        unreachable. A rogue receipt file is therefore ignored, not caught. That is pre-existing and
        is reported rather than changed here: editing manifest-pinned code within hours of maturity
        buys nothing, and the PREFIX check above is what actually protects the resume.
        """
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        harness.paths["receipt_dir"].mkdir(parents=True, exist_ok=True)
        W.atomic_write_json(W.receipt_path("not_a_stage", harness.paths["receipt_dir"]),
                            {"stage": "not_a_stage", "completed": True}, "rogue receipt")
        done = W.completed_stages(harness.paths["receipt_dir"])
        self.assertNotIn("not_a_stage", done)
        for stage in done:
            self.assertIn(stage, W.RUN_ORDER)

    def test_resume_after_a_clean_stage_boundary_continues_rather_than_repeating(self):
        """Crash strictly BETWEEN stages, then resume: the finished ones stay finished.

        The crash is injected around `run_stage` rather than inside the runner. Raising inside the
        runner is mid-stage: the pre-launch write has already set `stage_in_flight`, so a resume
        correctly quarantines with Q08 instead of continuing, which is a different test.
        """
        harness = Harness(self, [CUTOFF])
        stop_after = 2
        original = W.run_stage
        self.addCleanup(lambda: setattr(W, "run_stage", original))
        calls = {"n": 0}

        def crash_between(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] > stop_after:
                raise self.Boom("killed after a clean stage boundary")
            return original(*args, **kwargs)

        W.run_stage = crash_between
        with self.assertRaises(self.Boom):
            harness.watch(poll_seconds=1, max_iterations=1)
        # The crash is over: restore before resuming, or the resumed run dies in the same injection.
        W.run_stage = original
        done_before = W.completed_stages(harness.paths["receipt_dir"])
        self.assertEqual(done_before, list(W.RUN_ORDER[:stop_after]))
        resumed = Harness(self, [CUTOFF])
        state = resumed.watch(poll_seconds=1, max_iterations=1,
                              **{k: v for k, v in harness.paths.items()})
        self.assertEqual(state["state"], W.STATE_ALL_STAGES_COMPLETE)
        self.assertEqual(W.completed_stages(harness.paths["receipt_dir"]), list(W.RUN_ORDER))
        for argv in resumed.ran:
            self.assertNotIn(argv, done_before)
        self.assertEqual(len(resumed.ran), len(W.RUN_ORDER) - stop_after,
                         "only the unfinished stages may run on resume")


class ResumeTests(unittest.TestCase):
    """A partial artifact is not a checkpoint."""

    def test_a_stage_in_flight_quarantines_on_resume(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        state = json.loads(harness.paths["state_path"].read_text())
        state["stage_in_flight"] = "enumerate_creates"
        harness.paths["state_path"].write_text(json.dumps(state))
        with self.assertRaisesRegex(W.Quarantined, W.Q08_STAGE_INTERRUPTED):
            Harness(self, [CUTOFF - 1]).watch(poll_seconds=1, max_iterations=1, **harness.paths)

    def test_a_completed_prefix_resumes_from_the_next_stage(self):
        harness = Harness(self, [CUTOFF])
        harness.watch_all(poll_seconds=1, max_iterations=1)
        self.assertEqual(len(harness.ran), len(W.RUN_ORDER))
        resumed = Harness(self, [CUTOFF])
        resumed.directory = harness.directory
        resumed.watch_all(poll_seconds=1, max_iterations=1)
        self.assertEqual(resumed.ran, [])

    def test_a_failed_stage_writes_a_receipt_that_is_not_a_completion(self):
        harness = Harness(self, [CUTOFF], stage_exit=3)
        with self.assertRaisesRegex(W.Quarantined, W.Q07_STAGE_FAILED):
            harness.watch_all(poll_seconds=1, max_iterations=1)
        receipt = json.loads((harness.paths["receipt_dir"] / "program_boundary.json").read_text())
        self.assertFalse(receipt["completed"])
        self.assertEqual(receipt["exit_code"], 3)
        self.assertEqual(W.completed_stages(harness.paths["receipt_dir"]), [])

    def test_a_failed_stage_leaves_the_watcher_quarantined(self):
        harness = Harness(self, [CUTOFF], stage_exit=3)
        with self.assertRaises(W.Quarantined):
            harness.watch_all(poll_seconds=1, max_iterations=1)
        state = json.loads(harness.paths["state_path"].read_text())
        self.assertEqual(state["state"], W.STATE_QUARANTINED)
        resumed = Harness(self, [CUTOFF])
        resumed.directory = harness.directory
        with self.assertRaisesRegex(W.Quarantined, "quarantined"):
            resumed.watch_all(poll_seconds=1, max_iterations=1)

    def test_completed_stages_must_be_a_prefix_of_the_run_order(self):
        harness = Harness(self, [CUTOFF - 1])
        harness.watch(poll_seconds=1, max_iterations=1)
        harness.paths["receipt_dir"].mkdir(parents=True, exist_ok=True)
        receipts = harness.paths["receipt_dir"]
        receipts.mkdir(parents=True, exist_ok=True)
        (receipts / "simulator_replay_gate.json").write_text(
            json.dumps({"stage": "simulator_replay_gate", "completed": True}))
        state = json.loads(harness.paths["state_path"].read_text())
        with self.assertRaisesRegex(W.Quarantined, W.Q12_DUPLICATE_STAGE):
            W.assert_resume_is_safe(state, receipts)

    def test_the_state_file_is_written_atomically(self):
        """A half-written state file is not a state, so the write goes to a temporary path and is
        renamed."""
        source = (ROOT / "scripts" / "b11c_maturity_watcher.py").read_text()
        self.assertIn("os.replace(temporary, path)", source)


class IsolationTests(unittest.TestCase):
    """Every path a run writes to is a parameter, so a test can never touch the real directory."""

    def test_run_stage_writes_its_state_where_it_was_told(self):
        """It did not, once. `write_state` defaulted to the real supervisor state file, so a test
        run wrote into research/b11a/ — the one directory a test must never touch."""
        import inspect
        source = inspect.signature(W.run_stage)
        for name in ("log_dir", "receipt_dir", "state_path"):
            with self.subTest(parameter=name):
                self.assertIn(name, source.parameters)
        harness = Harness(self, [CUTOFF])
        harness.watch_all(poll_seconds=1, max_iterations=1)
        self.assertTrue(harness.paths["state_path"].exists())
        for receipt in W.RUN_ORDER:
            with self.subTest(stage=receipt):
                self.assertTrue((harness.paths["receipt_dir"] / f"{receipt}.json").exists())


class LivenessTests(unittest.TestCase):
    """A stored state says what the process was doing when it last wrote, not that it still is."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="b11c-live-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.state_path = self.dir / "state.json"
        self.lock_path = self.dir / "supervisor.lock"

    def write_state(self, **overrides):
        state = {"state": W.STATE_WAITING, "poll_seconds": 300,
                 "last_poll_at": int(__import__("time").time()), "polls": 3,
                 "last_tip_slot": CUTOFF - 100, "cutoff_slot_inclusive": CUTOFF,
                 "stage_in_flight": None, "quarantine": None,
                 "endpoint": "https://rpc.invalid", "results_unlocked": False,
                 "composition_published": False}
        state.update(overrides)
        self.state_path.write_text(json.dumps(state))
        return state

    def test_a_dead_process_is_never_reported_as_waiting(self):
        """The defect this exists for: a supervisor that died on Tuesday still saying 'waiting' on
        Friday, because status read a file and asked nothing else."""
        state = self.write_state()
        self.lock_path.write_text("999999")
        view = W.status(self.state_path, self.dir / "receipts", self.lock_path)
        self.assertEqual(view["liveness"], W.LIVENESS_DEAD)
        self.assertEqual(view["state"], W.LIVENESS_DEAD)
        self.assertEqual(view["reported_state"], state["state"])

    def test_a_pidfile_alone_is_not_proof(self):
        self.write_state()
        self.lock_path.write_text("999999")
        signals = W.liveness(json.loads(self.state_path.read_text()), self.lock_path)
        self.assertFalse(signals["pid_alive"])
        self.assertFalse(signals["lock_held"])

    def test_a_reused_pid_running_something_else_is_not_our_watcher(self):
        """A PID is reused within days; kill -0 succeeding says only that SOMETHING is there.

        This test process is itself the sharpest case: pytest's argv contains
        `tests/test_b11c_maturity_watcher.py`, so a check matching the module name alone would
        answer "yes" for the process asking the question."""
        self.write_state()
        self.lock_path.write_text(str(os.getpid()))
        self.assertFalse(W.process_is_this_watcher(os.getpid()))
        signals = W.liveness(json.loads(self.state_path.read_text()), self.lock_path)
        self.assertIn(signals["liveness"], (W.LIVENESS_DEAD, W.LIVENESS_STALE))

    def test_a_stale_heartbeat_is_not_alive(self):
        import time as _time
        self.write_state(last_poll_at=int(_time.time()) - 5_000)
        self.lock_path.write_text("999999")
        signals = W.liveness(json.loads(self.state_path.read_text()), self.lock_path)
        self.assertFalse(signals["heartbeat_fresh"])
        self.assertNotEqual(signals["liveness"], W.LIVENESS_ALIVE)

    def test_a_held_lock_with_no_heartbeat_is_stale_not_alive(self):
        """Signals that disagree are never 'running normally'."""
        import time as _time
        self.write_state(last_poll_at=int(_time.time()) - 5_000)
        with W.InstanceLock(self.lock_path):
            signals = W.liveness(json.loads(self.state_path.read_text()), self.lock_path)
        self.assertTrue(signals["lock_held"])
        self.assertEqual(signals["liveness"], W.LIVENESS_STALE)

    def test_no_state_at_all_reports_not_started(self):
        view = W.status(self.dir / "absent.json", self.dir / "receipts", self.lock_path)
        self.assertEqual(view["liveness"], W.LIVENESS_NOT_STARTED)
        self.assertEqual(view["state"], W.LIVENESS_NOT_STARTED)

    def test_an_empty_log_is_not_evidence_of_anything(self):
        """The watcher writes state, not chatter, so an empty log says nothing either way. The
        heartbeat is what carries the signal."""
        self.write_state()
        (self.dir / "logs").mkdir(exist_ok=True)
        (self.dir / "logs" / "watcher.stdout.log").write_text("")
        self.lock_path.write_text("999999")
        self.assertEqual(
            W.liveness(json.loads(self.state_path.read_text()),
                       self.lock_path)["liveness"], W.LIVENESS_DEAD)

    def test_the_three_signals_are_reported_individually(self):
        self.write_state()
        self.lock_path.write_text("999999")
        signals = W.liveness(json.loads(self.state_path.read_text()), self.lock_path)
        for field in ("pid_alive", "lock_held", "heartbeat_fresh", "heartbeat_age_seconds"):
            with self.subTest(field=field):
                self.assertIn(field, signals)


class ArchiveTests(unittest.TestCase):
    """A failed launch is evidence about how the supervisor behaves; never erase it."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="b11c-arch-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.state = self.dir / "state.json"
        self.lock = self.dir / "supervisor.lock"
        self.state.write_text(json.dumps({"state": W.STATE_WAITING}))
        self.lock.write_text("999999")

    def test_a_superseded_run_is_moved_aside_not_deleted(self):
        note = W.archive_run("stale launch", work_dir=self.dir, state_path=self.state,
                             lock_path=self.lock, archive_dir=self.dir / "superseded",
                             stamp="20260802T000000Z")
        self.assertFalse(self.state.exists())
        self.assertFalse(self.lock.exists())
        archived = self.dir / "superseded" / "20260802T000000Z"
        self.assertTrue((archived / "state.json").exists())
        self.assertTrue((archived / "supervisor.lock").exists())
        self.assertEqual(note["reason"], "stale launch")

    def test_a_run_with_completed_stages_is_never_archived(self):
        receipts = self.dir / "receipts"
        receipts.mkdir()
        (receipts / "program_boundary.json").write_text(
            json.dumps({"stage": "program_boundary", "completed": True}))
        with self.assertRaisesRegex(W.WatcherRefused, "cannot be repeated"):
            W.archive_run("x", work_dir=self.dir, state_path=self.state, lock_path=self.lock,
                          archive_dir=self.dir / "superseded")


class LockTests(unittest.TestCase):
    """Two supervisors would run every stage twice against a one-shot window."""

    def test_a_second_instance_is_refused(self):
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-lock-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "supervisor.lock"
        with W.InstanceLock(path):
            with self.assertRaisesRegex(W.WatcherRefused, "already holds"):
                with W.InstanceLock(path):
                    pass

    def test_the_pid_is_recorded_in_the_lock_file_itself(self):
        """One artifact, written under the lock by the process holding it, so the pid and the lock
        cannot disagree."""
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-pid-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        lock = directory / "supervisor.lock"
        with W.InstanceLock(lock):
            self.assertEqual(W.read_pid(lock), os.getpid())

    def test_a_lock_on_a_temporary_path_touches_nothing_outside_it(self):
        """The defect this replaced: a second `pid_path` argument defaulted to the module-level
        real path, which Python binds at IMPORT time — so a test passing only a temporary lock path
        still wrote to and then deleted the live watcher's pidfile, and rebinding the module global
        did not even help. With one file there is no second path to get wrong."""
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-iso-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        before = sorted(p.name for p in directory.iterdir())
        with W.InstanceLock(directory / "supervisor.lock"):
            pass
        after = sorted(p.name for p in directory.iterdir())
        self.assertEqual(after, before + ["supervisor.lock"])
        import inspect
        parameters = inspect.signature(W.InstanceLock.__init__).parameters
        self.assertEqual(list(parameters), ["self", "path"],
                         "a second path parameter is a second path to get wrong")

    def test_the_lock_is_released_on_exit(self):
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-lock-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "supervisor.lock"
        with W.InstanceLock(path):
            pass
        with W.InstanceLock(path):
            pass

    def test_it_is_an_os_lock_and_not_a_pidfile(self):
        """A pidfile survives a kill -9 and locks nobody out; a flock is released by the kernel."""
        source = (ROOT / "scripts" / "b11c_maturity_watcher.py").read_text()
        self.assertIn("fcntl.flock", source)
        self.assertIn("LOCK_EX | fcntl.LOCK_NB", source)


class ScopeTests(unittest.TestCase):
    """What this watcher does not do."""

    def test_it_never_unlocks_results(self):
        harness = Harness(self, [CUTOFF])
        state = harness.watch_all(poll_seconds=1, max_iterations=1)
        self.assertFalse(state["results_unlocked"])
        self.assertFalse(state["composition_published"])

    def test_no_result_stage_script_appears_in_any_stage_argv(self):
        joined = " ".join(part for command in W.stage_commands().values()
                          for part in command["argv"])
        for banned in ("b10b_path_dataset", "b10c_label_corpus", "b11b_"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, joined)

    def test_the_module_makes_no_call_outside_the_preflight(self):
        source = (ROOT / "scripts" / "b11c_maturity_watcher.py").read_text()
        for banned in ("requests", "urllib.request", "http.client", "socket."):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)
        self.assertIn("B11A.preflight_call", source)

    def test_the_poll_interval_is_conservative(self):
        self.assertGreaterEqual(W.DEFAULT_POLL_SECONDS, 300)

    def test_every_quarantine_code_is_declared(self):
        source = (ROOT / "scripts" / "b11c_maturity_watcher.py").read_text()
        for code in W.QUARANTINE_CODES:
            with self.subTest(code=code):
                self.assertIn(code, source)


if __name__ == "__main__":
    unittest.main()


class SupersedeStagesTests(unittest.TestCase):
    """Retiring stages so they run again, without destroying the record or breaking the prefix.

    Written against B11a: stage 1 collected an upgrade-boundary proof for a slot range the window
    it will be used against does not occupy, and stage 4 refused on a pin from another study. Both
    have to be redone and stages 2 and 3 must not be, because stage 2 is three days of collection.
    """

    def setUp(self):
        self.work = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.receipts = self.work / "receipts"
        self.receipts.mkdir()
        self.archive = self.work / "superseded"
        self.state_path = self.work / "supervisor_state.json"
        self.lock = self.work / "supervisor.lock"
        # Named from RUN_ORDER rather than hardcoded: these tests once said RUN_ORDER[:4] and
        # meant "up to signature_inventory", so inserting a stage silently re-aimed every one of
        # them at a different set. A slice is a claim about the order, not about the stages.
        self.done = list(W.RUN_ORDER[:3])
        self.failed = W.RUN_ORDER[3]
        self.first_four = self.done + [self.failed]
        for stage in self.done:
            self.write_receipt(stage, completed=True)
        self.write_receipt(self.failed, completed=False)
        self.state = {"stages_completed": list(self.done),
                      "stage_in_flight": None, "quarantine": None, "state": "running_stage"}
        self.write_state()

    def write_receipt(self, stage, completed):
        (self.receipts / f"{stage}.json").write_text(
            json.dumps({"stage": stage, "completed": completed, "exit_code": 0 if completed else 1}))

    def write_state(self):
        self.state_path.write_text(json.dumps(self.state))

    def supersede(self, names, reason="the boundary proof is for another window", **kwargs):
        return W.supersede_stages(
            names, reason, work_dir=self.work, state_path=self.state_path,
            archive_dir=self.archive, lock_path=self.lock, receipt_dir=self.receipts,
            stamp="20260808T010000Z", **kwargs)

    # -- the one this function exists for ---------------------------------------------------

    def test_it_refuses_the_plan_that_looks_obviously_right(self):
        """Supersede stage 1 and stage 4, keep 2 and 3. Every one of us agreed to this first.

        It leaves ['enumerate_creates', 'build_cohort'], which is not a prefix, and the supervisor
        would quarantine on Q12 at the next start -- with the receipts already moved. The refusal
        has to come BEFORE the move, which is what the second half of this test checks.
        """
        with self.assertRaisesRegex(W.WatcherRefused, "PREFIX"):
            self.supersede([W.RUN_ORDER[0], self.failed])
        self.assertEqual(
            sorted(p.name for p in self.receipts.iterdir()),
            sorted(f"{s}.json" for s in self.first_four),
            "the refusal must precede the move, or the operator learns of it too late")
        self.assertFalse(self.archive.exists())

    def test_the_message_names_the_quarantine_a_resume_would_hit(self):
        with self.assertRaises(W.WatcherRefused) as caught:
            self.supersede([W.RUN_ORDER[0], self.failed])
        self.assertIn(W.Q12_DUPLICATE_STAGE, str(caught.exception))

    def test_superseding_all_four_reaches_a_valid_prefix(self):
        """The route that satisfies the invariant instead of weakening it."""
        note = self.supersede(self.first_four)
        self.assertEqual(W.completed_stages(self.receipts), [])
        self.assertEqual(
            W.assert_resume_is_safe({"stage_in_flight": None}, self.receipts), [],
            "the empty list is a real prefix, so no rule had to be relaxed")
        self.assertEqual(note["stages_completed_before"],
                         ["program_boundary", "enumerate_creates", "build_cohort"])
        self.assertEqual(note["stages_completed_after"], [])

    def test_superseding_only_the_tail_is_permitted(self):
        """The ordinary case, and the one every other test here forgot to prove.

        A sweep caught this: every test above asserts the function says NO -- to a hole, an unknown
        stage, a held lock, an escape. None asserted it says YES to the plain case of retiring the
        LAST stage, which leaves a genuine prefix behind. A mutant that refused everything except
        an empty or complete list passed all of them, because refusing too much looks exactly like
        refusing correctly when refusal is all you ever check.

        This is also the case we would have used had stage 1's boundary proof been sound: only
        stage 4 needed redoing, and the function must permit that without argument.
        """
        note = self.supersede([self.failed], reason="the pin was from another study")
        remaining = W.completed_stages(self.receipts)
        self.assertEqual(remaining, self.done)
        self.assertEqual(W.assert_resume_is_safe({"stage_in_flight": None}, self.receipts),
                         remaining, "a proper prefix must be left alone, not rejected")
        self.assertEqual(note["stages_completed_after"], remaining)
        self.assertFalse((self.receipts / f"{self.failed}.json").exists())

    def test_nothing_is_deleted(self):
        self.supersede(self.first_four)
        archived = self.archive / "20260808T010000Z" / "receipts"
        self.assertEqual(sorted(p.name for p in archived.iterdir()),
                         sorted(f"{s}.json" for s in self.first_four))
        self.assertEqual(json.loads((archived / f"{self.failed}.json").read_text())["exit_code"],
                         1, "the FAILED receipt is evidence too; it is archived, not dropped")

    # -- artifacts ---------------------------------------------------------------------------

    def test_it_moves_named_artifacts_and_refuses_an_escape(self):
        artifact = self.work / "b11a_cohort.sqlite"
        artifact.write_bytes(b"cohort")
        self.supersede(self.first_four, artifacts=["b11a_cohort.sqlite"])
        self.assertFalse(artifact.exists())
        moved = self.archive / "20260808T010000Z" / "artifacts" / "b11a_cohort.sqlite"
        self.assertEqual(moved.read_bytes(), b"cohort")

    def test_an_artifact_outside_the_work_directory_is_refused(self):
        outside = self.work.parent / "not_ours.sqlite"
        outside.write_bytes(b"x")
        self.addCleanup(outside.unlink, missing_ok=True)
        with self.assertRaisesRegex(W.WatcherRefused, "outside"):
            self.supersede(self.first_four, artifacts=[str(outside)])
        self.assertTrue(outside.exists())

    def test_a_relative_escape_is_refused_after_resolution(self):
        """`../` would pass a textual containment check. The comparison is on resolved paths."""
        outside = self.work.parent / "escaped.sqlite"
        outside.write_bytes(b"x")
        self.addCleanup(outside.unlink, missing_ok=True)
        with self.assertRaisesRegex(W.WatcherRefused, "outside"):
            self.supersede(self.first_four, artifacts=["../escaped.sqlite"])
        self.assertTrue(outside.exists())

    def test_a_missing_artifact_is_refused_before_anything_moves(self):
        with self.assertRaisesRegex(W.WatcherRefused, "no artifact"):
            self.supersede(self.first_four, artifacts=["never_existed.sqlite"])
        self.assertEqual(len(list(self.receipts.iterdir())), 4)

    # -- refusals ----------------------------------------------------------------------------

    def test_it_refuses_while_a_supervisor_holds_the_lock(self):
        import fcntl
        self.lock.write_text("1234")
        handle = open(self.lock, "r+")
        self.addCleanup(handle.close)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        with self.assertRaisesRegex(W.WatcherRefused, "instance lock is held"):
            self.supersede(self.first_four)
        self.assertEqual(len(list(self.receipts.iterdir())), 4)

    def test_it_refuses_an_unknown_stage(self):
        with self.assertRaisesRegex(W.WatcherRefused, "unknown stage"):
            self.supersede([W.RUN_ORDER[0], "not_a_stage"])

    def test_it_refuses_superseding_nothing(self):
        with self.assertRaisesRegex(W.WatcherRefused, "superseding nothing"):
            self.supersede([])

    def test_it_refuses_a_stage_named_twice(self):
        with self.assertRaisesRegex(W.WatcherRefused, "named twice"):
            self.supersede([W.RUN_ORDER[0], W.RUN_ORDER[0]])

    def test_it_refuses_without_a_reason(self):
        for blank in ("", "   "):
            with self.assertRaisesRegex(W.WatcherRefused, "without a reason"):
                self.supersede(self.first_four, reason=blank)

    def test_it_refuses_a_stage_with_no_receipt(self):
        with self.assertRaisesRegex(W.WatcherRefused, "no receipt"):
            self.supersede(self.first_four + [W.RUN_ORDER[4]])

    def test_it_refuses_to_write_a_second_record_into_one_archive(self):
        self.supersede(self.first_four)
        for stage in self.done:
            self.write_receipt(stage, completed=True)
        self.write_receipt(self.failed, completed=False)
        with self.assertRaisesRegex(W.WatcherRefused, "already exists"):
            self.supersede(self.first_four)

    # -- the quarantine ----------------------------------------------------------------------

    def test_a_quarantined_run_refuses_unless_clearing_is_asked_for(self):
        self.state["quarantine"] = {"reason_code": "Q07_stage_failed",
                                    "stage": "signature_inventory"}
        self.write_state()
        with self.assertRaisesRegex(W.WatcherRefused, "clear_quarantine was not requested"):
            self.supersede(self.first_four)
        self.assertEqual(len(list(self.receipts.iterdir())), 4)

    def test_clearing_the_quarantine_records_it_verbatim(self):
        """Once the live state is cleared this note is the only surviving account of the stop."""
        quarantine = {"reason_code": "Q07_stage_failed", "stage": "signature_inventory",
                      "exit_code": 1}
        self.state["quarantine"] = quarantine
        self.write_state()
        note = self.supersede(self.first_four, clear_quarantine=True)
        self.assertEqual(note["quarantine_cleared"], quarantine)
        state = json.loads(self.state_path.read_text())
        self.assertIsNone(state["quarantine"])
        self.assertEqual(state["stages_completed"], [])

    def test_a_clean_run_records_no_quarantine_and_needs_no_permission(self):
        note = self.supersede(self.first_four)
        self.assertIsNone(note["quarantine_cleared"],
                          "nothing was cleared, so nothing may be recorded as cleared")

    def test_the_note_carries_the_reason_and_every_move(self):
        note = self.supersede(self.first_four, reason="stage 1 proved another window")
        self.assertEqual(note["reason"], "stage 1 proved another window")
        self.assertEqual(len(note["moved"]), 4)
        for entry in note["moved"]:
            self.assertTrue(pathlib.Path(entry["to"]).exists())
            self.assertFalse(pathlib.Path(entry["from"]).exists())
        written = json.loads(
            (self.archive / "20260808T010000Z" / "superseded.json").read_text())
        self.assertEqual(written, note, "the returned note and the durable one must be the same")


class EveryStageScriptIsPinnedTests(unittest.TestCase):
    """The manifest must cover every script the pipeline runs, derived rather than remembered.

    b11f_cohort_subsample.py was wired in as a stage and left out of MANIFEST_FILES. Nothing
    caught it: the list was hand-maintained and every OTHER stage script happened to be on it, so
    the omission looked like a complete list. The manifest exists to stop a stage script changing
    during a wait measured in days -- and the one file it was missing is the one that chooses which
    curves the study observes.
    """

    def test_every_script_named_in_a_stage_argv_is_manifest_pinned(self):
        commands = W.stage_commands(pathlib.Path("/tmp/b11a-iso"))
        for stage, command in commands.items():
            for part in command["argv"]:
                if part.endswith(".py") and part.startswith("scripts/"):
                    with self.subTest(stage=stage, script=part):
                        self.assertIn(
                            part, W.MANIFEST_FILES,
                            f"{part} runs as part of {stage} but is not pinned; it could change "
                            "during the wait and the run would proceed against different code")

    def test_the_check_would_notice_an_unpinned_script(self):
        """Non-vacuous: with a stage naming an unpinned script, the assertion must fail."""
        scripts = {part for command in W.stage_commands(pathlib.Path("/tmp/b11a-iso")).values()
                   for part in command["argv"]
                   if part.endswith(".py") and part.startswith("scripts/")}
        self.assertTrue(scripts, "the scan must actually find scripts, or it proves nothing")
        self.assertNotIn("scripts/not_pinned_anywhere.py", W.MANIFEST_FILES)


class StageArgvActuallyParsesTests(unittest.TestCase):
    """Every stage's argv must be one its script can parse, positionals included.

    b11e checks that every FLAG the plan passes is declared. It does not check bare tokens, so
    `b11f_cohort_subsample.py build --source ...` sailed through every offline check and died at
    run time with "unrecognized arguments: build" -- exit 2, after three stages had completed. I
    had copied b11d's `build` subcommand pattern onto a script that has no subcommands.

    A subcommand is a POSITIONAL, and the flag check was blind to positionals by construction.
    """

    def parsed_usage(self, script):
        """The script's own usage line, which names its subcommands in braces if it has any."""
        result = subprocess.run([sys.executable, script, "--help"], capture_output=True,
                                text=True, cwd=ROOT, timeout=60)
        return result.stdout + result.stderr

    def test_every_bare_token_in_a_stage_argv_is_a_subcommand_the_script_declares(self):
        commands = W.stage_commands(pathlib.Path("/tmp/b11a-iso"))
        for stage, command in commands.items():
            argv = command["argv"]
            script = next((a for a in argv if a.endswith(".py")), None)
            if not script:
                continue
            index = argv.index(script)
            bare = []
            skip_next = False
            for token in argv[index + 1:]:
                if skip_next:
                    skip_next = False
                    continue
                if token.startswith("-"):
                    skip_next = True          # assume the flag takes a value; harmless if it does not
                    continue
                bare.append(token)
            if not bare:
                continue
            usage = self.parsed_usage(script)
            for token in bare:
                if "/" in token or token.endswith((".sqlite", ".json", ".jsonl")):
                    continue                   # a path argument, not a subcommand
                with self.subTest(stage=stage, token=token):
                    self.assertIn(
                        token, usage,
                        f"{stage} passes bare token {token!r} to {script}, which does not declare "
                        "it. A stray positional passes every flag check and fails at run time")

    def test_the_check_would_have_caught_the_defect_it_was_written_for(self):
        """Non-vacuous: the exact broken argv must be rejected by the same logic."""
        usage = self.parsed_usage("scripts/b11f_cohort_subsample.py")
        self.assertNotIn("build", usage,
                         "b11f declares no `build` subcommand, which is why the original argv died")
        self.assertIn("--source", usage, "the scan must actually be reading a usage line")


class ReattestInPlaceTests(unittest.TestCase):
    """Adopting a new manifest without discarding the work already done.

    The gap that cost a launch: supersede retires stages and archive_run discards the state, so a
    restart re-freezes from zero. Both are right when the work must be redone and NEITHER is right
    when a pinned file changed for a reviewed reason and five stages are still valid -- re-freezing
    there re-runs the local stages, which refuse, because a cohort artifact is written once.
    """

    def setUp(self):
        self.work = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.receipts = self.work / "receipts"
        self.receipts.mkdir()
        self.archive = self.work / "superseded"
        self.state_path = self.work / "supervisor_state.json"
        self.lock = self.work / "supervisor.lock"
        self.done = list(W.RUN_ORDER[:3])
        for stage in self.done:
            (self.receipts / f"{stage}.json").write_text(
                json.dumps({"stage": stage, "completed": True}))
        self.state = {"stages_completed": list(self.done), "stage_in_flight": None,
                      "quarantine": None, "state": "running_stage",
                      "manifest_sha256": "stale" + "0" * 59}
        self.write_state()

    def write_state(self):
        self.state_path.write_text(json.dumps(self.state))

    def reattest(self, reason="a pinned file changed for a reviewed reason", **kwargs):
        return W.reattest_in_place(
            reason, work_dir=self.work, state_path=self.state_path, lock_path=self.lock,
            receipt_dir=self.receipts, archive_dir=self.archive, stamp="20260808T150000Z", **kwargs)

    # -- the thing it exists for -----------------------------------------------------------------

    def test_it_adopts_the_current_manifest_and_keeps_every_completed_stage(self):
        note = self.reattest()
        state = json.loads(self.state_path.read_text())
        self.assertEqual(state["manifest_sha256"], W.manifest_hash(W.build_manifest()))
        self.assertEqual(state["stages_completed"], self.done,
                         "the completed work must survive; re-running it is what this avoids")
        self.assertEqual(note["stages_preserved"], self.done)
        self.assertNotEqual(note["manifest_before"], note["manifest_after"])

    def test_the_prior_state_is_archived_not_overwritten(self):
        self.reattest()
        archived = self.archive / "20260808T150000Z" / "supervisor_state.before.json"
        self.assertTrue(archived.exists())
        self.assertEqual(json.loads(archived.read_text())["manifest_sha256"],
                         "stale" + "0" * 59)

    # -- refusals, each a way this could launder a mistake ---------------------------------------

    def test_it_computes_the_manifest_itself_and_takes_none_on_trust(self):
        """A re-attestation that accepts a hash attests what the caller believed, not the disk."""
        import inspect
        signature = inspect.signature(W.reattest_in_place)
        self.assertNotIn("manifest", signature.parameters)
        self.assertNotIn("manifest_sha256", signature.parameters)

    def test_an_unchanged_manifest_is_refused(self):
        self.state["manifest_sha256"] = W.manifest_hash(W.build_manifest())
        self.write_state()
        with self.assertRaisesRegex(W.WatcherRefused, "nothing changed"):
            self.reattest()

    def test_a_stage_in_flight_is_refused(self):
        self.state["stage_in_flight"] = "transaction_bodies"
        self.write_state()
        with self.assertRaisesRegex(W.WatcherRefused, "in flight"):
            self.reattest()

    def test_a_disagreement_between_state_and_receipts_is_refused(self):
        self.state["stages_completed"] = self.done[:2]
        self.write_state()
        with self.assertRaisesRegex(W.WatcherRefused, "receipts say"):
            self.reattest()

    def test_a_non_prefix_completed_set_is_refused(self):
        (self.receipts / f"{W.RUN_ORDER[0]}.json").unlink()
        self.state["stages_completed"] = list(W.RUN_ORDER[1:3])
        self.write_state()
        with self.assertRaisesRegex(W.WatcherRefused, "PREFIX"):
            self.reattest()

    def test_a_held_lock_is_refused(self):
        import fcntl
        self.lock.write_text("1")
        handle = open(self.lock, "r+")
        self.addCleanup(handle.close)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        with self.assertRaisesRegex(W.WatcherRefused, "instance lock is held"):
            self.reattest()

    def test_an_unexplained_reattestation_is_refused(self):
        with self.assertRaisesRegex(W.WatcherRefused, "without a reason"):
            self.reattest(reason="   ")

    def test_a_quarantine_is_not_cleared_unless_asked(self):
        self.state["quarantine"] = {"reason_code": "Q07_stage_failed"}
        self.write_state()
        with self.assertRaisesRegex(W.WatcherRefused, "clear_quarantine was not requested"):
            self.reattest()

    def test_clearing_records_the_quarantine_verbatim(self):
        quarantine = {"reason_code": "Q07_stage_failed", "stage": "transaction_bodies",
                      "exit_code": 1}
        self.state["quarantine"] = quarantine
        self.write_state()
        note = self.reattest(clear_quarantine=True)
        self.assertEqual(note["quarantine_cleared"], quarantine)
        state = json.loads(self.state_path.read_text())
        self.assertIsNone(state["quarantine"])
        self.assertEqual(state["stages_completed"], self.done, "clearing must not lose the work")

    def test_it_refuses_when_there_is_no_state_at_all(self):
        self.state_path.unlink()
        with self.assertRaisesRegex(W.WatcherRefused, "nothing to re-attest"):
            self.reattest()


class DirectoryOwnershipRefusalTests(unittest.TestCase):
    """The guard must REFUSE, and each refusal must be provable by a test that fails without it.

    Why these exist, stated plainly because the gap they close was invisible for a full green run:
    every other path that touches `assert_directory_is_claimable` drives it in the ALLOW direction.
    B11e's dry run builds a fixture corpus and expects the guard to succeed, so the suite could only
    ever catch a guard that wrongly REFUSES -- and it did catch exactly that twice, both fail-closed
    bugs. It was STRUCTURALLY BLIND to a guard that wrongly ALLOWS, which is the only failure mode
    that destroys a corpus.

    A peer mutation run proved the blindness rather than asserting it: disabling the fail-closed
    branch, the spent-tombstone branch, or the state-cutoff comparison each flipped the guard to
    ALLOW on its scenario, SILENTLY, with 4,403 tests still green. Every case below is one of those
    mutants' scenarios, so a fail-open regression now has to survive a test written to kill it.
    """

    def fixture(self, name="corpus"):
        directory = pathlib.Path(tempfile.mkdtemp(prefix=f"b11c-own-{name}-"))
        self.addCleanup(shutil.rmtree, directory, True)
        # A corpus, not bookkeeping: the databases are what cannot be collected again.
        (directory / "b11a_bodies.sqlite").write_bytes(b"SQLite format 3\x00")
        return directory

    def expected_cutoff(self, generation=1):
        return B11A.derive_window(
            W.generation_config(generation)["ranges"])["observation_cutoff_slot_inclusive"]

    def test_a_corpus_with_no_witness_at_all_is_refused(self):
        """M1 -- the git-clean hole itself.

        `supervisor_state.json` is gitignored, so a `git clean -fdx` removes it AND the receipts
        while leaving the databases. This is that directory, exactly.
        """
        directory = self.fixture("bare")
        with self.assertRaises(W.Quarantined) as caught:
            W.assert_directory_is_claimable(directory, 1, self.expected_cutoff())
        self.assertIn("already holds collection artifacts", str(caught.exception))

    def test_a_spent_tombstone_refuses_its_own_generation(self):
        """M2 -- re-collecting a window whose passes are spent."""
        directory = self.fixture("spent")
        (directory / W.SPENT_TOMBSTONE).write_text(json.dumps(
            {"generation": 1, "spent": True, "cutoff_slot_inclusive": self.expected_cutoff()}))
        with self.assertRaises(W.Quarantined) as caught:
            W.assert_directory_is_claimable(directory, 1, self.expected_cutoff())
        self.assertIn("tombstoned SPENT", str(caught.exception))

    def test_a_state_file_recording_another_window_is_refused(self):
        """M3 -- a run pointed at a corpus belonging to a different window."""
        directory = self.fixture("wrongstate")
        state = directory / "supervisor_state.json"
        state.write_text(json.dumps({"cutoff_slot_inclusive": self.expected_cutoff() + 1}))
        with self.assertRaises(W.Quarantined) as caught:
            W.assert_directory_is_claimable(directory, 1, self.expected_cutoff())
        self.assertIn("belongs to a different window", str(caught.exception))

    def test_a_tombstone_recording_another_window_is_refused_even_when_not_spent(self):
        """M4 -- the branch the other fixtures cannot reach.

        The spent-flag check sits above the cutoff comparison, so a spent tombstone is caught before
        the cutoff is ever compared. That ordering is deliberate belt-and-braces, but it makes the
        cutoff branch coverage-invisible unless a fixture reaches it: a tombstone whose window
        differs AND whose spent flag is false. Without this case, mutating that comparison survives.
        """
        directory = self.fixture("wrongtomb")
        (directory / W.SPENT_TOMBSTONE).write_text(json.dumps(
            {"generation": 2, "spent": False, "cutoff_slot_inclusive": self.expected_cutoff() + 1}))
        with self.assertRaises(W.Quarantined) as caught:
            W.assert_directory_is_claimable(directory, 1, self.expected_cutoff())
        self.assertIn("is tombstoned to generation", str(caught.exception))

    def test_an_unreadable_tombstone_forbids_rather_than_being_ignored(self):
        """A witness that cannot be read is not a witness that is absent."""
        directory = self.fixture("corrupt")
        (directory / W.SPENT_TOMBSTONE).write_text("{not json")
        with self.assertRaises(W.Quarantined):
            W.assert_directory_is_claimable(directory, 1, self.expected_cutoff())

    def test_bookkeeping_alone_does_not_trip_the_fail_closed_branch(self):
        """The other direction, so the guard is not merely refusing everything.

        Locks, pids and receipts are reconstructible. A directory holding only those has lost
        nothing, and refusing it would block legitimate fresh runs -- which is how a guard gets
        weakened by whoever hits it next.
        """
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-own-book-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "supervisor.lock").write_text("")
        (directory / "watcher.pid").write_text("1")
        self.assertEqual(directory,
                         W.assert_directory_is_claimable(directory, 1, self.expected_cutoff()))

    def test_an_empty_directory_is_claimable(self):
        directory = pathlib.Path(tempfile.mkdtemp(prefix="b11c-own-empty-"))
        self.addCleanup(shutil.rmtree, directory, True)
        self.assertEqual(directory,
                         W.assert_directory_is_claimable(directory, 1, self.expected_cutoff()))

    def test_the_injected_state_path_is_the_one_consulted(self):
        """A run with its own state path must not have live state read as ABSENT.

        That reading would send it down the fail-closed branch, so the guard would refuse the very
        run it exists to protect. This was a real bug in the first cut of the fix.
        """
        directory = self.fixture("injected")
        state = directory / "state.json"
        state.write_text(json.dumps({"cutoff_slot_inclusive": self.expected_cutoff()}))
        self.assertEqual(directory, W.assert_directory_is_claimable(
            directory, 1, self.expected_cutoff(), state_path=state))
