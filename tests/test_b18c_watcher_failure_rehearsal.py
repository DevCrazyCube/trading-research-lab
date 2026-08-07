"""Guards for B18c's watcher failure rehearsals.

Two things are being tested and they are not the same thing. First, that the supervisor classifies
and persists each fault the way it claims to. Second, and more important, that the harness itself
cannot lie: it runs against a COPY, it never touches the live watcher, and it may not credit a
quarantine code it did not cause. The first version did exactly that -- it read a code left behind
by an earlier rehearsal's state file and reported it as its own -- which is the fabricated-evidence
failure this project refuses everywhere else.
"""
import hashlib
import importlib.util
import json
import pathlib
import socket
import unittest
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B18C = _load("b18c_watcher_failure_rehearsal_under_test", "b18c_watcher_failure_rehearsal.py")
LIVE = ROOT / "scripts" / "b11c_maturity_watcher.py"


class LiveWatcherIsUntouchedTests(unittest.TestCase):
    """The property that makes this harness runnable while a watcher is live."""

    def test_the_live_watcher_is_byte_identical_after_a_full_sweep(self):
        before = hashlib.sha256(LIVE.read_bytes()).hexdigest()
        B18C.rehearse_all()
        self.assertEqual(hashlib.sha256(LIVE.read_bytes()).hexdigest(), before)

    def test_the_sweep_reports_the_digest_it_checked(self):
        report = B18C.rehearse_all()
        self.assertTrue(report["live_watcher_unchanged"])
        self.assertEqual(report["live_watcher_sha256_before"], report["live_watcher_sha256_after"])
        self.assertEqual(report["live_watcher_sha256_before"],
                         hashlib.sha256(LIVE.read_bytes()).hexdigest())

    def test_a_changed_original_is_refused_rather_than_reported(self):
        """If the harness ever did edit the live file, it must refuse, not carry on."""
        with self.assertRaises(B18C.RehearsalRefused) as refusal:
            B18C.assert_original_untouched("0" * 64)
        self.assertIn("changed during a rehearsal", str(refusal.exception))

    def test_staging_actually_calls_the_isolation_guard(self):
        """Read from the AST. The guard passing when called proves nothing if it is never called,
        and because the property always holds, deleting the call was invisible to every other test."""
        import ast
        tree = ast.parse((ROOT / "scripts" / "b18c_watcher_failure_rehearsal.py").read_text())
        staged = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.ClassDef) and node.name == "staged_watcher")
        enter = next(node for node in staged.body
                     if isinstance(node, ast.FunctionDef) and node.name == "__enter__")
        calls = {ast.unparse(node.func) for node in ast.walk(enter) if isinstance(node, ast.Call)}
        self.assertIn("assert_staged_isolation", calls)

    def test_the_staged_copy_cannot_reach_the_live_work_directory(self):
        """Structural, not careful: the copy's ROOT is the scratch tree, so WORK_DIR follows it."""
        with B18C.staged_watcher() as staged:
            self.assertEqual(staged.module.ROOT, staged.root)
            self.assertTrue(str(staged.module.WORK_DIR).startswith(str(staged.root)))
            self.assertNotEqual(staged.module.WORK_DIR, ROOT / "research" / "b11a")
            self.assertNotIn(ROOT, staged.module.WORK_DIR.parents)

    def test_the_staged_copy_is_byte_identical_to_the_original(self):
        """A copy that drifted would rehearse something other than the watcher."""
        with B18C.staged_watcher() as staged:
            copied = (staged.root / "scripts" / "b11c_maturity_watcher.py").read_bytes()
        self.assertEqual(hashlib.sha256(copied).hexdigest(),
                         hashlib.sha256(LIVE.read_bytes()).hexdigest())

    def test_the_scratch_tree_is_removed_afterwards(self):
        with B18C.staged_watcher() as staged:
            root = staged.root
            self.assertTrue(root.exists())
        self.assertFalse(root.exists())


class HarnessCannotFabricateTests(unittest.TestCase):
    """The bug that made this class necessary: a code credited to the wrong rehearsal."""

    def test_each_rehearsal_gets_its_own_state_file(self):
        with B18C.staged_watcher() as staged:
            _, first = staged.isolated("alpha")
            _, second = staged.isolated("beta")
            self.assertNotEqual(first, second)

    def test_reusing_a_state_label_is_refused(self):
        """Sharing a state file is how a leftover quarantine code got read as a fresh one."""
        with B18C.staged_watcher() as staged:
            _, path = staged.isolated("alpha")
            path.write_text("{}")
            with self.assertRaises(B18C.RehearsalRefused) as refusal:
                staged.isolated("alpha")
            self.assertIn("must not share state", str(refusal.exception))

    def test_every_credited_code_came_from_a_rehearsal_that_caused_it(self):
        """Cross-check the coverage claim against the individual results that justify it."""
        report = B18C.rehearse_all()
        coverage = report["quarantine_code_coverage"]
        justified = set()
        justified.add(report["retries_exhausted"]["reason_code"])
        justified.add(report["non_retryable"]["reason_code"])
        justified.add(report["manifest_drift"]["reason_code"])
        for entry in report["stage_lifecycle"].values():
            if isinstance(entry, dict) and entry.get("reason_code"):
                justified.add(entry["reason_code"])
        if all(report["non_finalized_slot"].values()):
            justified.add("Q04_non_finalized_slot")
        if all(report["secret_refusal"][case]["refused"]
               for case in ("full_url", "path_segment_only", "nested_in_a_diagnostic")):
            justified.add("Q09_secret_would_be_written")
        if report["composition_refusal"]["count_keyed_by_window_word"] == "refused":
            justified.add("Q10_composition_would_leak")
        if all(report["git_ancestry"][b]["refused"]
               for b in ("no_git_in_staged_tree", "commit_not_an_ancestor")):
            justified.add("Q03_git_ancestry_broken")
        self.assertEqual(set(coverage["reached"]), justified - {None})

    def test_unreached_codes_each_carry_a_reason(self):
        """Silence about a gap is the gap. Three are unreachable offline and each says why."""
        coverage = B18C.rehearse_all()["quarantine_code_coverage"]
        self.assertTrue(coverage["not_reached"])
        for code, reason in coverage["not_reached"].items():
            with self.subTest(code=code):
                self.assertGreater(len(reason.strip()), 30, "a reason must actually explain")

    def test_an_unexplained_unreached_code_refuses_rather_than_getting_a_default(self):
        """Forces the guard rather than trusting it. The default it replaced was dead code:
        every unreached code already had an explicit reason, so no fallback could ever be used."""
        with B18C.staged_watcher() as staged:
            with self.assertRaises(B18C.RehearsalRefused) as refusal:
                B18C.unreachable_codes(staged, reached=set())
            self.assertIn("neither reached nor explained", str(refusal.exception))

    def test_reached_and_not_reached_together_are_every_declared_code(self):
        coverage = B18C.rehearse_all()["quarantine_code_coverage"]
        self.assertEqual(sorted(set(coverage["reached"]) | set(coverage["not_reached"])),
                         sorted(coverage["declared"]))


class TransportClassificationTests(unittest.TestCase):
    """The two faults that killed real runs, and the policy that now decides them."""

    @classmethod
    def setUpClass(cls):
        cls.results = B18C.rehearse_all()["transport_classification"]

    def test_a_403_is_terminal(self):
        """Retrying a WAF refusal is how a run got banned."""
        self.assertFalse(self.results["provider_403"]["retryable"])

    def test_a_dns_failure_is_retryable_despite_matching_no_marker(self):
        """The exact fault that killed a run when classification was by message substring."""
        self.assertTrue(self.results["dns_failure"]["retryable"])
        self.assertNotIn("timed out", "Temporary failure in name resolution".lower())

    def test_a_tls_failure_is_retryable_for_the_same_reason(self):
        self.assertTrue(self.results["tls_failure"]["retryable"])

    def test_an_rpc_entitlement_refusal_is_terminal(self):
        """No retry changes an answer about who you are."""
        self.assertFalse(self.results["rpc_entitlement"]["retryable"])

    def test_an_rpc_node_behind_is_retryable(self):
        self.assertTrue(self.results["rpc_node_behind"]["retryable"])

    def test_no_diagnostic_carries_the_endpoint(self):
        """HTTPError.url holds the credential for this provider, and diagnostics reach disk."""
        for name, result in self.results.items():
            with self.subTest(fault=name):
                self.assertNotIn("rpc.example.com", result["diagnostic"])
                self.assertNotIn("redacted", result["diagnostic"])

    def test_a_mismatch_between_probe_and_policy_refuses(self):
        """Neither the harness nor the watcher is assumed right when they disagree."""
        with B18C.staged_watcher() as staged:
            saved = dict(B18C.TRANSPORT_FAULTS["provider_403"])
            B18C.TRANSPORT_FAULTS["provider_403"] = dict(saved, expected_retryable=True)
            self.addCleanup(B18C.TRANSPORT_FAULTS.__setitem__, "provider_403", saved)
            with self.assertRaises(B18C.RehearsalRefused) as refusal:
                B18C.rehearse_transport_classification(staged)
            self.assertIn("neither may be assumed correct", str(refusal.exception))


class QuarantineBehaviourTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.report = B18C.rehearse_all()

    def test_exhausted_retries_persist_the_reason_before_raising(self):
        """A supervisor that dies while its state file reads healthy is what happened once.

        The judgement is made HERE, from the state the harness observed, not read back from a
        boolean the harness computed. A mutant that hardcoded that boolean survived, because the
        test was reading the harness's opinion of itself.
        """
        result = self.report["retries_exhausted"]
        self.assertEqual(result["reason_code"], "Q05_retries_exhausted")
        self.assertEqual(result["persisted_state"], "quarantined")
        self.assertEqual(result["attempts"], 3)
        self.assertIn("Q05_retries_exhausted", result["refusal_message"])

    def test_backoff_is_exponential_and_bounded(self):
        self.assertEqual(self.report["retries_exhausted"]["backoff_sleeps"], [5, 10])

    def test_a_terminal_failure_does_not_burn_retries(self):
        """Derived here from the call count and the backoff list, not from a reported boolean."""
        result = self.report["non_retryable"]
        self.assertEqual(result["reason_code"], "Q06_non_retryable_rpc")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["backoff_sleeps"], [])

    def test_a_fault_that_clears_does_not_quarantine(self):
        """A guard that always fires is a stop, not a check."""
        result = self.report["recovers_before_exhausting"]
        self.assertIsNone(result["quarantined"])
        self.assertEqual(result["slot"], 435_800_000)

    def test_a_self_edit_under_a_waiting_supervisor_quarantines(self):
        """The supervisor pins ITSELF, because that file was once the blind spot."""
        result = self.report["manifest_drift"]
        self.assertTrue(result["quarantined"])
        self.assertEqual(result["reason_code"], "Q02_script_manifest_drift")
        self.assertEqual(result["persisted_state"], "quarantined")
        # The manifest was attested BEFORE the edit and differs after it. Compared here rather than
        # trusting a "passed_before_the_edit" flag the harness computed about itself.
        self.assertNotEqual(result["manifest_hash_attested_before_the_edit"],
                            result["manifest_hash_after_the_edit"])
        self.assertEqual(result["file_edited"], "scripts/b11c_maturity_watcher.py")

    def test_a_tip_that_is_not_an_integer_is_not_a_tip(self):
        for label, refused in self.report["non_finalized_slot"].items():
            with self.subTest(value=label):
                self.assertTrue(refused, f"{label} was accepted as a finalized slot")

    def test_a_failed_stage_writes_its_receipt_and_then_quarantines(self):
        """A stage nobody can audit is worse than one that failed visibly."""
        result = self.report["stage_lifecycle"]["stage_failed"]
        self.assertEqual(result["reason_code"], "Q07_stage_failed")
        self.assertEqual(result["exit_code_recorded"], 1)
        self.assertTrue(result["receipt_says_not_completed"])

    def test_a_kill_with_a_stage_in_flight_is_never_resumed(self):
        """A partial artifact is not a checkpoint."""
        result = self.report["stage_lifecycle"]["stage_interrupted"]
        self.assertEqual(result["reason_code"], "Q08_stage_interrupted")
        self.assertTrue(result["not_resumed"])

    def test_a_clean_shutdown_is_resumable(self):
        self.assertFalse(self.report["stage_lifecycle"]["clean_resume_allowed"]["refused"])

    def test_a_clean_stage_completes(self):
        """The happy path must work, or every refusal above proves only that nothing runs."""
        self.assertTrue(self.report["stage_lifecycle"]["clean_stage_completes"]["receipt_completed"])

    def test_an_unresolvable_stage_never_runs(self):
        result = self.report["stage_lifecycle"]["stage_wiring_unresolved"]
        self.assertEqual(result["reason_code"], "Q11_stage_wiring_unresolved")
        self.assertTrue(result["runner_never_called"])

    def test_a_stage_with_a_receipt_may_not_run_twice(self):
        result = self.report["stage_lifecycle"]["duplicate_stage"]
        self.assertEqual(result["reason_code"], "Q12_duplicate_stage")
        self.assertTrue(result["refused_before_running"])


class SecretAndCompositionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.report = B18C.rehearse_all()

    def test_the_path_segment_that_actually_leaked_is_refused(self):
        """b9d kept parsed.path and wrote a provider credential into a collected artifact."""
        result = self.report["secret_refusal"]["path_segment_only"]
        self.assertTrue(result["refused"])
        self.assertTrue(result["left_no_file"])
        self.assertTrue(result["left_no_partial"])

    def test_the_refusal_message_does_not_repeat_the_secret(self):
        """A guard that names what it refused to write has written it."""
        for label in ("full_url", "path_segment_only", "nested_in_a_diagnostic"):
            with self.subTest(case=label):
                self.assertTrue(self.report["secret_refusal"][label]["message_omits_the_secret"])

    def test_a_clean_payload_is_written(self):
        self.assertFalse(self.report["secret_refusal"]["clean"]["refused"])

    def test_a_count_keyed_by_a_window_word_is_refused(self):
        self.assertEqual(self.report["composition_refusal"]["count_keyed_by_window_word"], "refused")
        self.assertEqual(self.report["composition_refusal"]["nested_count"], "refused")

    def test_the_word_in_prose_is_not_a_leak_and_must_not_be_refused(self):
        """The stage is CALLED enumerate_creates; a scan firing on the word fires on itself.

        The same prose-versus-data distinction the execution-surface scanner had to learn. My first
        probe expected a refusal here and I reported the acceptance as a possible gap; it was my
        probe that was wrong.
        """
        self.assertEqual(self.report["composition_refusal"]["the_word_in_prose"], "accepted")
        self.assertEqual(self.report["composition_refusal"]["the_stage_name_itself"], "accepted")

    def test_a_boolean_is_not_a_count(self):
        self.assertEqual(self.report["composition_refusal"]["a_boolean_not_a_count"], "accepted")


class TwoClockLivenessTests(unittest.TestCase):

    def test_a_healthy_stage_does_not_read_as_a_dead_supervisor(self):
        """One clock read a whole healthy stage as death, because the poll loop stops during it."""
        result = B18C.rehearse_all()["two_clock_liveness"]
        # Both directions. While the stage ran, the heartbeat advanced and progress stood still;
        # once it actually progressed, the progress clock moved too. Showing only the first half
        # would not distinguish two clocks from one stuck one.
        self.assertGreater(result["heartbeat_while_stage_ran"], result["heartbeat_before"])
        self.assertEqual(result["progress_while_stage_ran"], result["progress_before"])
        self.assertGreater(result["progress_after_real_progress"],
                           result["progress_while_stage_ran"])
        self.assertGreater(result["heartbeat_after"], result["heartbeat_while_stage_ran"])
        self.assertEqual(result["state_keys"], ["stage_heartbeat_at", "stage_progress_at"])


class InternalGuardsAreForcedTests(unittest.TestCase):
    """Every guard inside the harness, made to fire.

    A mutation sweep found fifteen survivors here, nearly all of the same shape: a guard that only
    fires when something is wrong, in a harness where nothing is wrong, so deleting it changed
    nothing observable. The one mutant that DID die was the one whose bad condition a test forced.
    So each guard below is forced. Where a guard turned out to be genuinely unreachable it was
    removed instead, because a check that cannot fire reads as protection nobody tested.
    """

    def test_the_isolation_guard_refuses_a_root_outside_the_scratch_tree(self):
        """Calls the real guard with crafted paths. My first version re-implemented the check
        inline and raised its own exception, which tested nothing but the test."""
        with self.assertRaises(B18C.RehearsalRefused) as refusal:
            B18C.assert_staged_isolation(ROOT, ROOT / "research" / "b11a",
                                         pathlib.Path("/tmp/scratch"))
        self.assertIn("not the scratch tree", str(refusal.exception))

    def test_the_isolation_guard_refuses_a_work_dir_in_the_live_tree(self):
        scratch = pathlib.Path("/tmp/scratch")
        with self.assertRaises(B18C.RehearsalRefused) as refusal:
            B18C.assert_staged_isolation(scratch, ROOT / "research" / "b11a", scratch)
        self.assertIn("inside the live tree", str(refusal.exception))

    def test_the_isolation_guard_refuses_a_work_dir_outside_the_scratch_tree(self):
        scratch = pathlib.Path("/tmp/scratch")
        with self.assertRaises(B18C.RehearsalRefused) as refusal:
            B18C.assert_staged_isolation(scratch, pathlib.Path("/tmp/somewhere-else"), scratch)
        self.assertIn("outside the scratch tree", str(refusal.exception))

    def test_the_isolation_guard_accepts_a_real_staged_copy(self):
        """It must be satisfiable, or it is a stop rather than a check."""
        with B18C.staged_watcher() as staged:
            self.assertTrue(B18C.assert_staged_isolation(
                staged.module.ROOT, staged.module.WORK_DIR, staged.root))

    def test_the_root_and_workdir_guards_are_what_stand_up_the_copy(self):
        """Both conditions are checked on every stage, and both hold for a real staged copy."""
        with B18C.staged_watcher() as staged:
            self.assertEqual(staged.module.ROOT, staged.root)
            self.assertFalse(str(staged.module.WORK_DIR).startswith(str(ROOT / "research")))

    def test_a_diagnostic_carrying_the_endpoint_is_refused(self):
        """Forced by making a fault whose diagnostic would leak, so the guard has to fire."""
        with B18C.staged_watcher() as staged:
            saved = dict(B18C.TRANSPORT_FAULTS)
            leaky = urllib.error.URLError("connect failed to rpc.example.com")
            B18C.TRANSPORT_FAULTS["leaky_probe"] = {
                "error": leaky, "expected_retryable": True, "note": "forces the endpoint guard"}
            self.addCleanup(lambda: (B18C.TRANSPORT_FAULTS.clear(),
                                     B18C.TRANSPORT_FAULTS.update(saved)))
            with self.assertRaises(B18C.RehearsalRefused) as refusal:
                B18C.rehearse_transport_classification(staged)
            self.assertIn("must never be recorded", str(refusal.exception))

    def test_a_composition_probe_that_disagrees_with_the_guard_is_refused(self):
        """Neither the probe nor b11c is assumed right when they disagree."""
        with B18C.staged_watcher() as staged:
            original = staged.module.assert_no_composition
            staged.module.assert_no_composition = lambda payload, where: True
            self.addCleanup(setattr, staged.module, "assert_no_composition", original)
            with self.assertRaises(B18C.RehearsalRefused) as refusal:
                B18C.rehearse_composition_refusal(staged)
            self.assertIn("neither may be assumed correct", str(refusal.exception))

    def test_a_secret_that_gets_written_refuses_the_rehearsal(self):
        """The most important guard here: if b11c ever stopped refusing, this must not pass."""
        with B18C.staged_watcher() as staged:
            original = staged.module.assert_no_secret
            staged.module.assert_no_secret = lambda text, where: True
            self.addCleanup(setattr, staged.module, "assert_no_secret", original)
            with self.assertRaises(B18C.RehearsalRefused) as refusal:
                B18C.rehearse_secret_refusal(staged)
            self.assertIn("carrying the credential was written", str(refusal.exception))

    def test_a_clean_payload_being_refused_also_refuses_the_rehearsal(self):
        """The other direction. A secret guard that refuses everything is a stop, not a guard."""
        with B18C.staged_watcher() as staged:
            original = staged.module.assert_no_secret

            def refuse_everything(text, where):
                raise staged.module.WatcherRefused("refusing everything")

            staged.module.assert_no_secret = refuse_everything
            self.addCleanup(setattr, staged.module, "assert_no_secret", original)
            with self.assertRaises(B18C.RehearsalRefused) as refusal:
                B18C.rehearse_secret_refusal(staged)
            self.assertIn("a guard that always fires is a stop", str(refusal.exception))

    def test_the_secret_catch_is_narrow_enough_to_expose_a_harness_bug(self):
        """A TypeError must NOT read as a refusal. It did once, and hid a real bug for a full run."""
        with B18C.staged_watcher() as staged:
            original = staged.module.atomic_write_json

            def wrong_arity(*args, **kwargs):
                raise TypeError("atomic_write_json() missing 1 required positional argument")

            staged.module.atomic_write_json = wrong_arity
            self.addCleanup(setattr, staged.module, "atomic_write_json", original)
            with self.assertRaises(TypeError):
                B18C.rehearse_secret_refusal(staged)

    def test_q04_is_not_credited_unless_every_probe_refuses(self):
        """`all`, not `any`: one accepted non-integer tip means the guard has a hole."""
        report = B18C.rehearse_all()
        probes = report["non_finalized_slot"]
        self.assertTrue(all(probes.values()))
        self.assertGreaterEqual(len(probes), 4)
        partial = dict(probes, negative=False)
        self.assertFalse(all(partial.values()),
                         "the credit rule must distinguish a partial pass from a full one")


class PrimaryEvidenceTests(unittest.TestCase):
    """The same facts, observed directly instead of read out of the harness's report.

    Every mutant that survived after two rounds of fixing had the same shape: it faked a value in
    the harness's return dict, and the test read that value back. Deriving the judgement in the test
    did not help, because the input to the derivation still came from the thing under test. A test
    can only catch that by getting the evidence itself.

    So these drive the staged watcher directly and read the state file b11c actually wrote. They
    duplicate what the report claims on purpose: the report is a convenience, and this is the check.
    """

    def setUp(self):
        self.staged = B18C.staged_watcher().__enter__()
        self.addCleanup(self.staged.__exit__, None, None, None)

    def test_the_state_file_on_disk_says_quarantined_after_exhausted_retries(self):
        state, path = self.staged.isolated("primary_retries")
        transport = B18C.raising_transport(B18C.http_error(503))
        slept = []
        with self.assertRaises(self.staged.module.Quarantined):
            self.staged.module.poll_with_backoff(
                "https://rpc.example.com:8899", transport=transport, retries=3,
                sleeper=slept.append, state=state, state_path=path)
        persisted = json.loads(path.read_text())
        self.assertEqual(persisted["state"], "quarantined")
        self.assertEqual(persisted["quarantine"]["reason_code"], "Q05_retries_exhausted")
        self.assertEqual(transport.calls["n"], 3)
        self.assertEqual(slept, [5, 10])

    def test_a_terminal_failure_really_calls_the_transport_once(self):
        state, path = self.staged.isolated("primary_terminal")
        transport = B18C.raising_transport(RuntimeError("RPC error -32002: refused"))
        slept = []
        with self.assertRaises(self.staged.module.Quarantined):
            self.staged.module.poll_with_backoff(
                "https://rpc.example.com:8899", transport=transport, retries=6,
                sleeper=slept.append, state=state, state_path=path)
        self.assertEqual(transport.calls["n"], 1)
        self.assertEqual(slept, [])
        self.assertEqual(json.loads(path.read_text())["quarantine"]["reason_code"],
                         "Q06_non_retryable_rpc")

    def test_the_manifest_hash_really_changes_when_the_supervisor_is_edited(self):
        before = self.staged.module.manifest_hash(self.staged.module.build_manifest())
        target = self.staged.root / "scripts" / "b11c_maturity_watcher.py"
        target.write_text(target.read_text() + "\n# edited\n")
        after = self.staged.module.manifest_hash(self.staged.module.build_manifest())
        self.assertNotEqual(before, after)

        state, path = self.staged.isolated("primary_manifest")
        state["manifest_sha256"] = before
        with self.assertRaises(self.staged.module.Quarantined):
            self.staged.module.assert_manifest_unchanged(state, path)
        self.assertEqual(json.loads(path.read_text())["quarantine"]["reason_code"],
                         "Q02_script_manifest_drift")

    def test_the_two_clocks_really_move_independently(self):
        state, path = self.staged.isolated("primary_clocks")
        start = 1_786_000_000
        self.staged.module.touch_stage_heartbeat(state, path, progressed=True, now=start)
        heartbeat_before = state["stage_heartbeat_at"]
        progress_before = state["stage_progress_at"]
        self.staged.module.touch_stage_heartbeat(state, path, progressed=False, now=start + 120)
        self.assertGreater(state["stage_heartbeat_at"], heartbeat_before)
        self.assertEqual(state["stage_progress_at"], progress_before)

    def test_every_non_integer_tip_is_really_refused(self):
        for label, value in (("boolean_true", True), ("negative", -1),
                             ("string", "435800000"), ("null", None)):
            with self.subTest(value=label):
                with self.assertRaises(self.staged.module.Quarantined):
                    self.staged.module.poll_finalized_slot(
                        "https://rpc.example.com:8899", transport=lambda *a, _v=value, **k: _v)

    def test_a_valid_tip_is_really_accepted(self):
        """Otherwise the four refusals above prove only that nothing is ever accepted."""
        self.assertEqual(self.staged.module.poll_finalized_slot(
            "https://rpc.example.com:8899", transport=lambda *a, **k: 435_800_000), 435_800_000)

    def test_the_credential_path_segment_is_really_refused_on_disk(self):
        import os
        endpoint = "https://solana-mainnet.example.com/a1b2c3d4e5f6a7b8c9d0e1f2"
        previous = os.environ.get(self.staged.module.RPC_ENV_VAR)
        os.environ[self.staged.module.RPC_ENV_VAR] = endpoint
        self.addCleanup(lambda: os.environ.__setitem__(self.staged.module.RPC_ENV_VAR, previous)
                        if previous is not None
                        else os.environ.pop(self.staged.module.RPC_ENV_VAR, None))
        path = self.staged.module.WORK_DIR / "primary_secret.json"
        with self.assertRaises(self.staged.module.WatcherRefused):
            self.staged.module.atomic_write_json(
                path, {"endpoint_reference": "/a1b2c3d4e5f6a7b8c9d0e1f2"}, "primary")
        self.assertFalse(path.exists())

    def test_verify_git_ancestry_really_refuses_a_tree_with_no_git(self):
        """Driven directly, not read out of the harness's report.

        Two mutants survived here -- faking the call and faking its result -- because every Q03 test
        I wrote read the reported dict. That is the same defect this class exists for, and I hit it
        again writing new code two rounds after diagnosing it. The report is a convenience; the
        check is calling b11c.
        """
        self.assertFalse((pathlib.Path(self.staged.root) / ".git").exists())
        with self.assertRaises(self.staged.module.Quarantined) as refusal:
            self.staged.module.verify_git_ancestry()
        self.assertIn("Q03_git_ancestry_broken", str(refusal.exception))
        self.assertIn("no commit", str(refusal.exception))

    def test_verify_git_ancestry_really_refuses_a_non_ancestor_commit(self):
        class Result:
            def __init__(self, stdout="", returncode=0):
                self.stdout, self.returncode = stdout, returncode

        def not_an_ancestor(*args):
            return Result(stdout="deadbeef\n") if args[0] == "log" else Result(returncode=1)

        with self.assertRaises(self.staged.module.Quarantined) as refusal:
            self.staged.module.verify_git_ancestry(git=not_an_ancestor)
        self.assertIn("not an ancestor", str(refusal.exception))

    def test_verify_git_ancestry_really_accepts_a_real_ancestor(self):
        class Result:
            def __init__(self, stdout="", returncode=0):
                self.stdout, self.returncode = stdout, returncode

        def clean(*args):
            return Result(stdout="cafebabe\n") if args[0] == "log" else Result(returncode=0)

        self.assertEqual(self.staged.module.verify_git_ancestry(git=clean),
                         {"preregistration_commit": "cafebabe"})

    def test_a_count_keyed_by_a_window_word_is_really_refused(self):
        with self.assertRaises(self.staged.module.Quarantined):
            self.staged.module.assert_no_composition({"curve_count": 1136}, "primary")
        self.assertTrue(self.staged.module.assert_no_composition(
            {"note": "12345 creates enumerated"}, "primary"))


class CreditsAreWithheldTests(unittest.TestCase):
    """The credit rule, given reports where a rehearsal did NOT justify the credit.

    Inline in `rehearse_all` these conditions were always true, so mutating them to `True` changed
    nothing any test could see. As a function taking a report, each one can be forced.
    """

    def setUp(self):
        self.report = B18C.rehearse_all()
        with B18C.staged_watcher() as staged:
            self.codes = staged.module

    def test_the_real_report_credits_what_it_should(self):
        self.assertEqual(B18C.credited_codes(self.report, self.codes),
                         self.report["quarantine_code_coverage"]["reached"])

    def test_q04_is_withheld_when_one_probe_was_accepted(self):
        """`all`, not `any`: one accepted non-integer tip is a hole, not a partial pass."""
        doctored = dict(self.report,
                        non_finalized_slot=dict(self.report["non_finalized_slot"], negative=False))
        self.assertNotIn("Q04_non_finalized_slot", B18C.credited_codes(doctored, self.codes))

    def test_q09_is_withheld_when_one_credential_payload_was_written(self):
        secret = json.loads(json.dumps(self.report["secret_refusal"]))
        secret["path_segment_only"]["refused"] = False
        doctored = dict(self.report, secret_refusal=secret)
        self.assertNotIn("Q09_secret_would_be_written", B18C.credited_codes(doctored, self.codes))

    def test_q10_is_withheld_when_the_count_was_accepted(self):
        doctored = dict(self.report,
                        composition_refusal=dict(self.report["composition_refusal"],
                                                 count_keyed_by_window_word="accepted"))
        self.assertNotIn("Q10_composition_would_leak", B18C.credited_codes(doctored, self.codes))

    def test_a_stage_code_is_withheld_when_the_stage_did_not_refuse(self):
        doctored = dict(self.report, stage_lifecycle={"stage_failed": {"refused": False}})
        self.assertNotIn("Q07_stage_failed", B18C.credited_codes(doctored, self.codes))

    def test_an_empty_report_credits_nothing(self):
        self.assertEqual(B18C.credited_codes({}, self.codes), [])


class ReportMatchesPrimaryEvidenceTests(unittest.TestCase):
    """Cross-check the harness's report against evidence gathered independently.

    The gap this closes: `PrimaryEvidenceTests` proves b11c behaves correctly and never reads the
    report, while the report tests read the report and never check it. A mutant that faked a value
    in the report slipped between the two. This class runs both and requires them to agree.
    """

    @classmethod
    def setUpClass(cls):
        cls.report = B18C.rehearse_all()

    def setUp(self):
        self.staged = B18C.staged_watcher().__enter__()
        self.addCleanup(self.staged.__exit__, None, None, None)

    def test_the_reported_persisted_state_matches_what_b11c_writes(self):
        state, path = self.staged.isolated("crosscheck_retries")
        transport = B18C.raising_transport(B18C.http_error(503))
        slept = []
        with self.assertRaises(self.staged.module.Quarantined):
            self.staged.module.poll_with_backoff(
                "https://rpc.example.com:8899", transport=transport, retries=3,
                sleeper=slept.append, state=state, state_path=path)
        observed = json.loads(path.read_text())["state"]
        self.assertEqual(self.report["retries_exhausted"]["persisted_state"], observed)
        self.assertEqual(self.report["retries_exhausted"]["attempts"], transport.calls["n"])
        self.assertEqual(self.report["retries_exhausted"]["backoff_sleeps"], slept)

    def test_the_reported_terminal_attempt_count_matches_the_transport(self):
        state, path = self.staged.isolated("crosscheck_terminal")
        transport = B18C.raising_transport(RuntimeError("RPC error -32002: refused"))
        slept = []
        with self.assertRaises(self.staged.module.Quarantined):
            self.staged.module.poll_with_backoff(
                "https://rpc.example.com:8899", transport=transport, retries=6,
                sleeper=slept.append, state=state, state_path=path)
        self.assertEqual(self.report["non_retryable"]["attempts"], transport.calls["n"])
        self.assertEqual(self.report["non_retryable"]["backoff_sleeps"], slept)

    def test_the_reported_manifest_hashes_match_a_fresh_computation(self):
        """The attested hash must be the unedited one, recomputed here rather than trusted."""
        clean = self.staged.module.manifest_hash(self.staged.module.build_manifest())
        self.assertEqual(self.report["manifest_drift"]["manifest_hash_attested_before_the_edit"],
                         clean)
        self.assertNotEqual(self.report["manifest_drift"]["manifest_hash_after_the_edit"], clean)

    def test_the_reported_clocks_match_an_independent_touch(self):
        """Reproduces all three touches the rehearsal makes, and requires every reported timestamp
        to match. A cross-check that mirrors only part of the scenario compares the wrong moments."""
        state, path = self.staged.isolated("crosscheck_clocks")
        module = self.staged.module
        start = 1_786_000_000
        module.touch_stage_heartbeat(state, path, progressed=True, now=start)
        first = dict(state)
        module.touch_stage_heartbeat(state, path, progressed=False,
                                     now=start + module.STAGE_HEARTBEAT_SECONDS * 4)
        still = dict(state)
        module.touch_stage_heartbeat(state, path, progressed=True,
                                     now=start + module.STAGE_HEARTBEAT_SECONDS * 8)

        reported = self.report["two_clock_liveness"]
        self.assertEqual(reported["heartbeat_before"], first["stage_heartbeat_at"])
        self.assertEqual(reported["progress_before"], first["stage_progress_at"])
        self.assertEqual(reported["heartbeat_while_stage_ran"], still["stage_heartbeat_at"])
        self.assertEqual(reported["progress_while_stage_ran"], still["stage_progress_at"])
        self.assertEqual(reported["heartbeat_after"], state["stage_heartbeat_at"])
        self.assertEqual(reported["progress_after_real_progress"], state["stage_progress_at"])


class GitAncestryTests(unittest.TestCase):
    """Q03, which this harness wrongly called unreachable in a committed artifact.

    The original reason read: "needs a rewritten git history in the scratch tree, which would prove
    nothing about the real one". That is true of the not-an-ancestor branch and false of the other:
    the staged tree has no `.git` at all, so verify_git_ancestry finds no commit and quarantines
    immediately. I inferred "unreachable" from one branch and stated it about the whole code. The
    codex seat found it by accident while staging for G7.
    """

    @classmethod
    def setUpClass(cls):
        cls.report = B18C.rehearse_all()

    def test_a_staged_tree_with_no_git_quarantines(self):
        result = self.report["git_ancestry"]["no_git_in_staged_tree"]
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason_code"], "Q03_git_ancestry_broken")
        # The REAL message, not a label the harness chose. b11c says "has no commit"; a faked
        # refusal does not, and two mutants survived until this compared the actual text.
        self.assertIn("has no commit", result["refusal_message"])
        self.assertIn("nobody can show was frozen first", result["refusal_message"])

    def test_the_reported_refusal_matches_an_independent_call(self):
        """Cross-check: the harness's text must equal what calling b11c directly produces."""
        with B18C.staged_watcher() as staged:
            try:
                staged.module.verify_git_ancestry()
                self.fail("verify_git_ancestry did not refuse in a tree with no git")
            except staged.module.Quarantined as refusal:
                observed = str(refusal)
        self.assertEqual(self.report["git_ancestry"]["no_git_in_staged_tree"]["refusal_message"],
                         observed)

    def test_the_accepted_ancestor_matches_an_independent_call(self):
        """Kills the mutant that fakes the accepted result instead of calling b11c."""
        class Result:
            def __init__(self, stdout="", returncode=0):
                self.stdout, self.returncode = stdout, returncode

        def clean(*args):
            return Result(stdout="cafebabe\n") if args[0] == "log" else Result(returncode=0)

        with B18C.staged_watcher() as staged:
            observed = staged.module.verify_git_ancestry(git=clean)
        self.assertEqual(self.report["git_ancestry"]["a_real_ancestor_is_accepted"], observed)

    def test_a_commit_that_is_not_an_ancestor_quarantines(self):
        result = self.report["git_ancestry"]["commit_not_an_ancestor"]
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason_code"], "Q03_git_ancestry_broken")
        self.assertIn("not an ancestor of HEAD", result["refusal_message"])

    def test_a_real_ancestor_is_accepted(self):
        """Or the guard is a stop rather than a check."""
        self.assertIn("preregistration_commit",
                      self.report["git_ancestry"]["a_real_ancestor_is_accepted"])

    def test_q03_is_now_credited_and_no_longer_listed_unreachable(self):
        coverage = self.report["quarantine_code_coverage"]
        self.assertIn("Q03_git_ancestry_broken", coverage["reached"])
        self.assertNotIn("Q03_git_ancestry_broken", coverage["not_reached"])

    def test_q03_is_withheld_when_only_one_branch_refuses(self):
        """Crediting a code for half a guard is the same error as crediting it for none."""
        with B18C.staged_watcher() as staged:
            doctored = dict(self.report, git_ancestry={
                "no_git_in_staged_tree": {"refused": True},
                "commit_not_an_ancestor": {"refused": False}})
            self.assertNotIn("Q03_git_ancestry_broken",
                             B18C.credited_codes(doctored, staged.module))

    def test_only_two_codes_remain_unreachable(self):
        coverage = self.report["quarantine_code_coverage"]
        self.assertEqual(sorted(coverage["not_reached"]),
                         ["Q01_preregistration_drift", "Q13_ambiguous_failure"])


class SweepSafetyTests(unittest.TestCase):

    def test_the_sweep_opens_no_socket(self):
        opened = []
        original = socket.socket
        socket.socket = lambda *a, **k: opened.append(1) or original(*a, **k)
        self.addCleanup(setattr, socket, "socket", original)
        B18C.rehearse_all()
        self.assertEqual(opened, [])

    def test_the_closure_has_no_execution_surface(self):
        report = B18C.rehearse_all()
        self.assertEqual(report["no_execution_surface"]["execution_surface_found"], {})
        self.assertIn("not a repository-wide", report["no_execution_surface"]["scope"])

    def test_the_report_never_claims_to_be_evidence(self):
        report = B18C.rehearse_all()
        self.assertIs(report["executable"], False)
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertIn("constructed by this file", report["record_is_not_evidence"])

    def test_the_sweep_is_deterministic(self):
        first = json.dumps(B18C.rehearse_all(), sort_keys=True, default=str)
        second = json.dumps(B18C.rehearse_all(), sort_keys=True, default=str)
        self.assertEqual(first, second)

    def test_nothing_under_the_live_work_directory_is_created(self):
        """The strongest form: the live research/b11a must be untouched by a sweep."""
        live = ROOT / "research" / "b11a"
        before = sorted(p.name for p in live.iterdir()) if live.exists() else []
        B18C.rehearse_all()
        after = sorted(p.name for p in live.iterdir()) if live.exists() else []
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
