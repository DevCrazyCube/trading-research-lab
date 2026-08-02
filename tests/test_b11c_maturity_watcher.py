"""Tests for the B11c maturity watcher and collection supervisor.

Nothing here touches a network. Every RPC call goes through an injected fake transport and every
stage through an injected fake runner, so the whole state machine — including maturity, retries,
quarantine and resume — is exercised without a single real request.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

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

    def test_every_consumer_is_pointed_at_the_cohort_artifact(self):
        commands = W.stage_commands(pathlib.Path("/tmp/b11a-iso"))
        for stage in ("signature_inventory", "transaction_bodies", "decode_and_reserves",
                      "reserve_coverage_gate"):
            with self.subTest(stage=stage):
                joined = " ".join(commands[stage]["argv"])
                self.assertIn("b11a_cohort.sqlite", joined)

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
        with self.assertRaisesRegex(W.WatcherRefused, "no scheme or host"):
            W.endpoint_receipt("not-a-url")


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
        view = W.status(harness.paths["state_path"], harness.paths["receipt_dir"])
        self.assertEqual(view["state"], W.STATE_ALL_STAGES_COMPLETE)
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
        self.pid_path = self.dir / "watcher.pid"
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
        self.pid_path.write_text("999999")
        view = W.status(self.state_path, self.dir / "receipts", self.pid_path, self.lock_path)
        self.assertEqual(view["liveness"], W.LIVENESS_DEAD)
        self.assertEqual(view["state"], W.LIVENESS_DEAD)
        self.assertEqual(view["reported_state"], state["state"])

    def test_a_pidfile_alone_is_not_proof(self):
        self.write_state()
        self.pid_path.write_text("999999")
        signals = W.liveness(json.loads(self.state_path.read_text()), self.pid_path,
                             self.lock_path)
        self.assertFalse(signals["pid_alive"])
        self.assertFalse(signals["lock_held"])

    def test_a_reused_pid_running_something_else_is_not_our_watcher(self):
        """A PID is reused within days; kill -0 succeeding says only that SOMETHING is there.

        This test process is itself the sharpest case: pytest's argv contains
        `tests/test_b11c_maturity_watcher.py`, so a check matching the module name alone would
        answer "yes" for the process asking the question."""
        self.write_state()
        self.pid_path.write_text(str(os.getpid()))
        self.assertFalse(W.process_is_this_watcher(os.getpid()))
        signals = W.liveness(json.loads(self.state_path.read_text()), self.pid_path,
                             self.lock_path)
        self.assertIn(signals["liveness"], (W.LIVENESS_DEAD, W.LIVENESS_STALE))

    def test_a_stale_heartbeat_is_not_alive(self):
        import time as _time
        self.write_state(last_poll_at=int(_time.time()) - 5_000)
        self.pid_path.write_text("999999")
        signals = W.liveness(json.loads(self.state_path.read_text()), self.pid_path,
                             self.lock_path)
        self.assertFalse(signals["heartbeat_fresh"])
        self.assertNotEqual(signals["liveness"], W.LIVENESS_ALIVE)

    def test_a_held_lock_with_no_heartbeat_is_stale_not_alive(self):
        """Signals that disagree are never 'running normally'."""
        import time as _time
        self.write_state(last_poll_at=int(_time.time()) - 5_000)
        with W.InstanceLock(self.lock_path):
            self.pid_path.write_text("999999")
            signals = W.liveness(json.loads(self.state_path.read_text()), self.pid_path,
                                 self.lock_path)
        self.assertTrue(signals["lock_held"])
        self.assertEqual(signals["liveness"], W.LIVENESS_STALE)

    def test_no_state_at_all_reports_not_started(self):
        view = W.status(self.dir / "absent.json", self.dir / "receipts", self.pid_path,
                        self.lock_path)
        self.assertEqual(view["liveness"], W.LIVENESS_NOT_STARTED)
        self.assertEqual(view["state"], W.LIVENESS_NOT_STARTED)

    def test_an_empty_log_is_not_evidence_of_anything(self):
        """The watcher writes state, not chatter, so an empty log says nothing either way. The
        heartbeat is what carries the signal."""
        self.write_state()
        (self.dir / "logs").mkdir(exist_ok=True)
        (self.dir / "logs" / "watcher.stdout.log").write_text("")
        self.pid_path.write_text("999999")
        self.assertEqual(
            W.liveness(json.loads(self.state_path.read_text()), self.pid_path,
                       self.lock_path)["liveness"], W.LIVENESS_DEAD)

    def test_the_three_signals_are_reported_individually(self):
        self.write_state()
        self.pid_path.write_text("999999")
        signals = W.liveness(json.loads(self.state_path.read_text()), self.pid_path,
                             self.lock_path)
        for field in ("pid_alive", "lock_held", "heartbeat_fresh", "heartbeat_age_seconds"):
            with self.subTest(field=field):
                self.assertIn(field, signals)


class ArchiveTests(unittest.TestCase):
    """A failed launch is evidence about how the supervisor behaves; never erase it."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="b11c-arch-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.state = self.dir / "state.json"
        self.pid = self.dir / "watcher.pid"
        self.state.write_text(json.dumps({"state": W.STATE_WAITING}))
        self.pid.write_text("999999")

    def test_a_superseded_run_is_moved_aside_not_deleted(self):
        note = W.archive_run("stale launch", work_dir=self.dir, state_path=self.state,
                             pid_path=self.pid, archive_dir=self.dir / "superseded",
                             stamp="20260802T000000Z")
        self.assertFalse(self.state.exists())
        self.assertFalse(self.pid.exists())
        archived = self.dir / "superseded" / "20260802T000000Z"
        self.assertTrue((archived / "state.json").exists())
        self.assertTrue((archived / "watcher.pid").exists())
        self.assertEqual(note["reason"], "stale launch")

    def test_a_run_with_completed_stages_is_never_archived(self):
        receipts = self.dir / "receipts"
        receipts.mkdir()
        (receipts / "program_boundary.json").write_text(
            json.dumps({"stage": "program_boundary", "completed": True}))
        with self.assertRaisesRegex(W.WatcherRefused, "cannot be repeated"):
            W.archive_run("x", work_dir=self.dir, state_path=self.state, pid_path=self.pid,
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
