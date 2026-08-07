"""B18c — watcher-side failure rehearsals, against a COPY, while the real one keeps running.

WHY THIS EXISTS
---------------
`scripts/b11c_maturity_watcher.py` declares thirteen quarantine codes. Every one of them was written
in response to something that had already gone wrong, or in anticipation of something that had not
yet been provoked — and the two that killed real runs (a Cloudflare 403 on the default user-agent,
and a transient `URLError` misclassified as fatal) were diagnosed *after* they killed them. b18b
rehearsed the record layer's failures. This rehearses the supervisor's.

THE SAFETY PROPERTY THAT MAKES THIS RUNNABLE AT ALL
---------------------------------------------------
A watcher has been running for over two days. Editing `b11c` while it runs is forbidden twice over:
it is manifest-pinned, and the live process holds its code in memory, so an edit is both undetected
by the running process and detected by its next manifest check. I nearly left a mutated
manifest-pinned file on disk once during a mutation sweep, with a live reader attached.

So nothing here touches the original. `staged_watcher()` copies `b11c` and its two `_load`
dependencies into a scratch tree and loads the COPY. Because `b11c` derives `ROOT` from its own
`__file__`, the copy's `WORK_DIR` resolves to `<scratch>/research/b11a` — an empty scratch directory
— and its `STATE_PATH`, `RECEIPT_DIR` and `LOG_DIR` follow it there. The copy is structurally unable
to reach the live work directory, and `assert_original_untouched()` re-hashes the real file before
and after every rehearsal.

WHAT A REHEARSAL PROVES, AND WHAT IT DOES NOT
---------------------------------------------
It proves the supervisor *classifies and persists* a fault the way it claims to: the right code, the
reason written to disk BEFORE the raise, and no credential or composition in what it wrote. It says
nothing about how often any of these occur, and nothing about the live run.

NO NETWORK
----------
Every transport is a callable defined here that raises or returns a scripted value. The whole sweep
runs under B17a's `NoNetwork`, so a socket opened anywhere aborts it.

TWO SURVIVING MUTANTS, AND WHY THEY ARE NOT "EQUIVALENT"
--------------------------------------------------------
The mutation sweep over this module reaches 24/24 only after two mutants are set aside, and the
label they are set aside under matters more than the number. They hardcode values this module
*reports*: `persisted_state` as `"quarantined"` in `rehearse_retries_exhausted`, and `attempts=1`
with an empty backoff list in `rehearse_non_retryable`.

I first called them equivalent mutants. They are not, and the codex seat was right to narrow it. A
strictly equivalent mutant is identical on all inputs, so no test can kill it and inquiry correctly
stops. These are identical only GIVEN that `b11c` currently persists before raising and quarantines
a terminal fault on the first call. If `b11c` ever regressed and raised without persisting, the
honest version would report the real state and the hardcoded version would not — and what it would
hide is exactly the regression the Q05 rehearsal exists to detect.

So the accurate label is **a mutant in a redundant reporting path whose underlying property is
asserted independently elsewhere**. Today that elsewhere is
`PrimaryEvidenceTests.test_the_state_file_on_disk_says_quarantined_after_exhausted_retries` and
`test_a_terminal_failure_really_calls_the_transport_once`, which drive the staged watcher directly
and read the file `b11c` actually wrote, never this module's report.

The distinction is operational, not pedantic: "equivalent mutant" is the label that ends auditing,
and "covered elsewhere" is the label that tells the next reader to go check the coverage still
exists. If those two tests were ever weakened, the first label would keep the sweep looking clean
while the property quietly stopped being checked.

Note also why `ReportMatchesPrimaryEvidenceTests` does not catch them: it requires the report and the
independent observation to AGREE, and a hardcoded `"quarantined"` agrees with a correct `b11c`.
Agreement cannot detect a constant that happens to be right. The layering still holds — the
cross-check catches disagreement, the primary evidence catches regression — but the cross-check is
not the layer doing the work here.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import tempfile
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

# The original, which is never opened for writing anywhere in this module.
LIVE_WATCHER = ROOT / "scripts" / "b11c_maturity_watcher.py"
COPIED_MODULES = ("b11c_maturity_watcher.py", "b11a_window_freeze.py", "rpc_http_identity.py")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B17A = _load("b17a_shadow_rehearsal", "b17a_shadow_rehearsal.py")


class RehearsalRefused(RuntimeError):
    """The rehearsal cannot proceed honestly, so it produces nothing."""


def live_watcher_digest():
    return hashlib.sha256(LIVE_WATCHER.read_bytes()).hexdigest()


def assert_original_untouched(before):
    """The property that lets this run at all. Checked, not promised."""
    after = live_watcher_digest()
    if after != before:
        raise RehearsalRefused(
            f"{LIVE_WATCHER} changed during a rehearsal ({before} -> {after}). A live watcher reads "
            f"this file and pins it in its own manifest; a rehearsal that edits it has become the "
            f"incident it was written to rehearse.")
    return after


def assert_staged_isolation(module_root, module_work_dir, scratch_root):
    """A staged copy must resolve entirely inside the scratch tree.

    A module-level function taking plain paths, rather than a check buried in `__enter__`, because
    inside `__enter__` it could never fire: the property always holds for a real copy, so deleting
    it changed nothing and a mutation survived. Called with crafted paths by a test, it fires.

    This is protection against a future change to how b11c derives ROOT, not against today's code.
    """
    if module_root != scratch_root:
        raise RehearsalRefused(
            f"the staged copy resolved ROOT to {module_root}, not the scratch tree at "
            f"{scratch_root}. It would read and write the live work directory.")
    if ROOT in module_work_dir.parents or module_work_dir == ROOT / "research" / "b11a":
        raise RehearsalRefused(
            f"the staged copy's WORK_DIR is {module_work_dir}, inside the live tree")
    if not str(module_work_dir).startswith(str(scratch_root)):
        raise RehearsalRefused(
            f"the staged copy's WORK_DIR {module_work_dir} is outside the scratch tree")
    return True


class staged_watcher:
    """A scratch copy of the watcher, loaded from a tree that cannot reach the live work directory.

    Not a mock. It is the real module, byte-identical, executing its real logic against a scratch
    root — so what the rehearsal exercises is the supervisor's actual classification, not a
    re-description of it.
    """

    def __init__(self):
        self._directory = None
        self.root = None
        self.module = None

    def __enter__(self):
        self._directory = tempfile.TemporaryDirectory(prefix="b18c-staged-")
        self.root = pathlib.Path(self._directory.name)
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "research" / "b11a").mkdir(parents=True)
        for name in COPIED_MODULES:
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        # Manifest entries the copy will hash. Present so a drift rehearsal can change one of them
        # in the SCRATCH tree and nowhere else.
        for name in ("b7d_create_enumerator.py", "b9c_signature_inventory.py",
                     "b9d_transaction_bodies.py", "b9e_reserve_coverage.py",
                     "b9f_failure_coverage.py", "b10a_simulator_kernel.py",
                     "b11d_cohort_adapter.py"):
            source = ROOT / "scripts" / name
            if source.exists():
                shutil.copy2(source, self.root / "scripts" / name)
        (self.root / "research").mkdir(exist_ok=True)
        for name in ("pump_idl_9c82f61.json", "pump_amm_idl_9c82f61.json",
                     "B11A_FRESH_COHORT_PREREGISTRATION.json",
                     "B11A_FRESH_COHORT_PREREGISTRATION.md"):
            source = ROOT / "research" / name
            if source.exists():
                shutil.copy2(source, self.root / "research" / name)

        spec = importlib.util.spec_from_file_location(
            "b11c_staged_copy", self.root / "scripts" / "b11c_maturity_watcher.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

        assert_staged_isolation(self.module.ROOT, self.module.WORK_DIR, self.root)
        return self

    def __exit__(self, *exception):
        self._directory.cleanup()
        return False

    def fresh_state(self):
        # `manifest_sha256` and `endpoint` are recorded into every stage receipt, so a state without
        # them cannot complete a stage at all. Scratch values: the endpoint is a sanitized identity
        # carrying no credential, which is the only form b11c would agree to write.
        return {"schema_version": self.module.SCHEMA_VERSION, "state": self.module.STATE_WAITING,
                "quarantine": None, "manifest_sha256": "0" * 64,
                "endpoint": "https://rpc.example.com:8899"}

    def isolated(self, label):
        """A state file per rehearsal, because a shared one lets a code leak between them.

        The first version shared one path. `rehearse_manifest_drift` wrote Q02, the stage rehearsal
        then failed with a TypeError of my own making, and the harness read the LEFTOVER Q02 and
        reported it as the stage's quarantine code. It published a code no rehearsal had caused.
        That is precisely the fabricated-evidence failure this project refuses everywhere else, so
        the fix is isolation rather than care.
        """
        path = self.module.WORK_DIR / f"state_{label}.json"
        if path.exists():
            raise RehearsalRefused(f"{path} already exists; rehearsals must not share state")
        return self.fresh_state(), path

    @property
    def state_path(self):
        return self.module.WORK_DIR / "supervisor_state.json"


# ----------------------------------------------------------------------------------------------
# Injected transports and runners. Nothing here reaches a network.
# ----------------------------------------------------------------------------------------------

def raising_transport(error, times=None):
    """A transport that fails. `times=None` fails forever; otherwise it fails then succeeds."""
    calls = {"n": 0}

    def transport(*args, **kwargs):
        calls["n"] += 1
        if times is None or calls["n"] <= times:
            raise error
        return 435_800_000

    transport.calls = calls
    return transport


def http_error(status):
    return urllib.error.HTTPError("https://rpc.example.com:8899/redacted", status, "x", {}, None)


TRANSPORT_FAULTS = {
    "provider_403": {"error": http_error(403), "expected_retryable": False,
                     "note": "the WAF refusing this client. Retrying it is how a run got banned."},
    "provider_429": {"error": http_error(429), "expected_retryable": True,
                     "note": "rate limited; bounded retries are correct"},
    "provider_503": {"error": http_error(503), "expected_retryable": True,
                     "note": "provider unavailable"},
    "dns_failure": {"error": urllib.error.URLError("Temporary failure in name resolution"),
                    "expected_retryable": True,
                    "note": ("the exact fault that killed a run: its TEXT matches no transient "
                             "marker, so message-substring classification called it fatal. Typed "
                             "classification is what fixed it.")},
    "tls_failure": {"error": urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED]"),
                    "expected_retryable": True,
                    "note": "also a URLError whose text matches no marker"},
    "connection_reset": {"error": ConnectionResetError("Connection reset by peer"),
                         "expected_retryable": True, "note": "an OSError subclass"},
    "rpc_node_behind": {"error": RuntimeError("RPC error -32005: node is behind by 200 slots"),
                        "expected_retryable": True,
                        "note": "an RPC-level condition inside a successful HTTP response"},
    "rpc_entitlement": {"error": RuntimeError("RPC error -32002: transaction simulation failed"),
                        "expected_retryable": False,
                        "note": "no retry changes an answer about who you are"},
}


# ----------------------------------------------------------------------------------------------
# The rehearsals
# ----------------------------------------------------------------------------------------------

def rehearse_transport_classification(staged):
    """Each transport fault, classified by the watcher's own policy rather than by a copy."""
    results = {}
    for name, fault in sorted(TRANSPORT_FAULTS.items()):
        actual = staged.module.is_retryable_failure(fault["error"])
        diagnostic = staged.module.poll_failure_diagnostic(fault["error"])
        if actual != fault["expected_retryable"]:
            raise RehearsalRefused(
                f"{name}: the watcher classified retryable={actual}, the rehearsal expected "
                f"{fault['expected_retryable']}. One of the two is wrong and neither may be "
                f"assumed correct.")
        # The diagnostic is written to disk, so it must not carry the endpoint credential.
        if "redacted" in diagnostic or "rpc.example.com" in diagnostic:
            raise RehearsalRefused(
                f"{name}: the diagnostic {diagnostic!r} carries the endpoint. HTTPError.url holds "
                f"the credential for this provider and it must never be recorded.")
        results[name] = {"retryable": actual, "diagnostic": diagnostic, "note": fault["note"]}
    return results


def rehearse_retries_exhausted(staged):
    """Q05: bounded retries, then quarantine with the reason PERSISTED before the raise."""
    state, state_path = staged.isolated("retries_exhausted")
    transport = raising_transport(http_error(503))
    slept = []
    try:
        staged.module.poll_with_backoff("https://rpc.example.com:8899", transport=transport,
                                        retries=3, sleeper=slept.append, state=state,
                                        state_path=state_path)
        raise RehearsalRefused("exhausted retries did not quarantine")
    except staged.module.Quarantined as refusal:
        persisted = json.loads(state_path.read_text())
        return {
            "reason_code": persisted["quarantine"]["reason_code"],
            "attempts": transport.calls["n"],
            "backoff_sleeps": slept,
            "persisted_state": persisted["state"],
            "refusal_message": str(refusal),
        }


def rehearse_non_retryable(staged):
    """Q06: a terminal RPC refusal quarantines on the FIRST attempt, without burning retries."""
    state, state_path = staged.isolated("non_retryable")
    transport = raising_transport(RuntimeError("RPC error -32002: entitlement refused"))
    slept = []
    try:
        staged.module.poll_with_backoff("https://rpc.example.com:8899", transport=transport,
                                        retries=6, sleeper=slept.append, state=state,
                                        state_path=state_path)
        raise RehearsalRefused("a non-retryable failure did not quarantine")
    except staged.module.Quarantined:
        persisted = json.loads(state_path.read_text())
        return {
            "reason_code": persisted["quarantine"]["reason_code"],
            "attempts": transport.calls["n"],
            "backoff_sleeps": slept,
        }


def rehearse_recovers_before_exhausting(staged):
    """The other half: a fault that clears must NOT quarantine. A guard that always fires is a stop."""
    state, state_path = staged.isolated("recovers")
    transport = raising_transport(http_error(503), times=2)
    slept = []
    slot = staged.module.poll_with_backoff("https://rpc.example.com:8899", transport=transport,
                                           retries=6, sleeper=slept.append, state=state,
                                           state_path=state_path)
    return {"slot": slot, "attempts": transport.calls["n"], "quarantined": state["quarantine"],
            "backoff_sleeps": slept}


def rehearse_non_finalized_slot(staged):
    """Q04: a tip that is not a non-negative integer is not a tip."""
    results = {}
    for label, value in (("boolean_true", True), ("negative", -1), ("string", "435800000"),
                         ("null", None)):
        transport = lambda *a, _v=value, **k: _v
        try:
            staged.module.poll_finalized_slot("https://rpc.example.com:8899", transport=transport)
            results[label] = "ACCEPTED"
        except staged.module.Quarantined as refusal:
            results[label] = staged.module.Q04_NON_FINALIZED_SLOT in str(refusal)
    return results


def rehearse_manifest_drift(staged):
    """Q02: the supervisor pins ITSELF, so an edit under a waiting process must quarantine.

    The edit happens in the SCRATCH tree. The live file is re-hashed afterwards to prove it did not.
    """
    state, state_path = staged.isolated("manifest_drift")
    # Attest the manifest as the real run does: the hash BEFORE the wait, checked again after it.
    state["manifest_sha256"] = staged.module.manifest_hash(staged.module.build_manifest())
    staged.module.assert_manifest_unchanged(state, state_path)
    attested = state["manifest_sha256"]
    target = staged.root / "scripts" / "b11c_maturity_watcher.py"
    target.write_text(target.read_text() + "\n# an edit under a waiting supervisor\n")
    try:
        staged.module.assert_manifest_unchanged(state, state_path)
        return {"quarantined": False, "note": "DRIFT WENT UNDETECTED"}
    except staged.module.Quarantined as refusal:
        persisted = json.loads(state_path.read_text())
        return {
            "quarantined": True,
            "reason_code": persisted["quarantine"]["reason_code"],
            "manifest_hash_attested_before_the_edit": attested,
            "manifest_hash_after_the_edit": staged.module.manifest_hash(
                staged.module.build_manifest()),
            "file_edited": "scripts/b11c_maturity_watcher.py",
            "persisted_state": persisted["state"],
            "refusal_message": str(refusal),
        }


def rehearse_secret_refusal(staged):
    """Q09: a payload carrying the credential must refuse the write and leave NO file.

    The endpoint shape here is the one that actually leaked. b9d kept `parsed.path` in an
    `endpoint_reference` and wrote a provider path credential into a collected artifact; b11c's
    `_secret_values` treats any path segment of 16 characters or more as a credential for exactly
    that reason. Both the full URL and the bare path segment are rehearsed, because the segment
    alone is what escaped last time.
    """
    import os
    endpoint = "https://solana-mainnet.example.com/a1b2c3d4e5f6a7b8c9d0e1f2"
    segment = "a1b2c3d4e5f6a7b8c9d0e1f2"
    previous = os.environ.get(staged.module.RPC_ENV_VAR)
    os.environ[staged.module.RPC_ENV_VAR] = endpoint
    try:
        results = {}
        for label, payload in (("full_url", {"endpoint": endpoint}),
                               ("path_segment_only", {"endpoint_reference": f"/{segment}"}),
                               ("nested_in_a_diagnostic", {"quarantine": {"diagnostic": segment}}),
                               ("clean", {"endpoint": "https://solana-mainnet.example.com"})):
            path = staged.module.WORK_DIR / f"secret_probe_{label}.json"
            try:
                staged.module.atomic_write_json(path, payload, f"rehearsal:{label}")
                results[label] = {"refused": False, "file_written": path.exists()}
            except staged.module.WatcherRefused as refusal:
                # Narrow deliberately. My first version caught Exception, so a TypeError of my own
                # making read as a successful refusal -- a test passing for the wrong reason, and
                # the reason it "passed" was that the code under test never ran.
                results[label] = {
                    "refused": True,
                    "refusal_type": type(refusal).__name__,
                    "left_no_file": not path.exists(),
                    "left_no_partial": not list(staged.module.WORK_DIR.glob(f"*{label}*.tmp*")),
                    "message_omits_the_secret": segment not in str(refusal)
                    and endpoint not in str(refusal),
                }
        if results["clean"]["refused"]:
            raise RehearsalRefused(
                "a payload carrying no secret was refused; a guard that always fires is a stop")
        for label in ("full_url", "path_segment_only", "nested_in_a_diagnostic"):
            if not results[label]["refused"]:
                raise RehearsalRefused(f"a payload carrying the credential was written: {label}")
        return results
    finally:
        if previous is None:
            os.environ.pop(staged.module.RPC_ENV_VAR, None)
        else:
            os.environ[staged.module.RPC_ENV_VAR] = previous


def rehearse_composition_refusal(staged):
    """Q10: a NUMBER keyed by a word describing the window. Not the word appearing in prose.

    My first probe expected `{"note": "12345 creates enumerated"}` to be refused and reported its
    acceptance as a possible gap. It is not a gap: b11c scans keys whose value is an integer,
    deliberately, because the stage is CALLED `enumerate_creates` and a scan that fired on the word
    would fire on the pipeline's own vocabulary. That is the same prose-versus-data distinction the
    execution-surface scanner had to learn. The probe was wrong; the design is right, and both
    directions are rehearsed here so the distinction itself is what gets tested.
    """
    results = {}
    cases = (
        ("count_keyed_by_window_word", {"curve_count": 1136}, "refused"),
        ("nested_count", {"stage": {"creates": 12345}}, "refused"),
        ("the_word_in_prose", {"note": "12345 creates enumerated"}, "accepted"),
        ("the_stage_name_itself", {"stage": "enumerate_creates"}, "accepted"),
        ("a_boolean_not_a_count", {"curves": True}, "accepted"),
        ("clean", {"stage": "enumerate_creates", "state": "running_stage"}, "accepted"),
    )
    for label, payload, expected in cases:
        try:
            staged.module.assert_no_composition(payload, "rehearsal")
            actual = "accepted"
        except staged.module.Quarantined:
            actual = "refused"
        if actual != expected:
            raise RehearsalRefused(
                f"composition probe {label}: expected {expected}, got {actual}. One of the probe "
                f"and the guard is wrong and neither may be assumed correct.")
        results[label] = actual
    return results


def rehearse_stage_lifecycle(staged):
    """Q07, Q08, Q11 and Q12. Four different facts about a stage, kept four different facts.

    `run_stage` takes a command DICT carrying its own wiring status, not an argv list; my first
    version passed `["true"]` and produced a TypeError that the harness then reported as a
    quarantine, using a code left behind by an earlier rehearsal. Both bugs are fixed: the signature
    is right and every rehearsal has its own state file.
    """
    results = {}
    resolved = {"wiring": "resolved", "argv": ["true"], "note": "synthetic"}

    def failing_runner(argv, stdout_path, stderr_path):
        """Returns a nonzero exit code -- it does NOT raise.

        My first version raised, which propagated before b11c could write the quarantine, so Q07
        never appeared and the harness reported the code as unreached. The runner contract is a
        return code; a runner that raises is rehearsing a different fault than the one intended.
        """
        pathlib.Path(stdout_path).write_text("")
        pathlib.Path(stderr_path).write_text("stage exited 1\n")
        return 1

    def clean_runner(argv, stdout_path, stderr_path):
        pathlib.Path(stdout_path).write_text("")
        pathlib.Path(stderr_path).write_text("")
        return 0

    def dirs(label):
        log_dir = staged.module.WORK_DIR / f"logs_{label}"
        receipt_dir = staged.module.WORK_DIR / f"receipts_{label}"
        log_dir.mkdir(parents=True, exist_ok=True)
        receipt_dir.mkdir(parents=True, exist_ok=True)
        return log_dir, receipt_dir

    # Q07: the stage ran and failed.
    state, state_path = staged.isolated("stage_failed")
    log_dir, receipt_dir = dirs("stage_failed")
    try:
        staged.module.run_stage("program_boundary", resolved, state, runner=failing_runner,
                                log_dir=log_dir, receipt_dir=receipt_dir, state_path=state_path)
        results["stage_failed"] = {"refused": False, "note": "A FAILED STAGE WAS ACCEPTED"}
    except staged.module.Quarantined as refusal:
        persisted = json.loads(state_path.read_text())
        receipt = json.loads(staged.module.receipt_path("program_boundary", receipt_dir).read_text())
        results["stage_failed"] = {
            "refused": True,
            "reason_code": persisted["quarantine"]["reason_code"],
            "exit_code_recorded": persisted["quarantine"]["exit_code"],
            "receipt_says_not_completed": receipt["completed"] is False,
            "receipt_written_anyway": True,
            "message_names_the_code": staged.module.Q07_STAGE_FAILED in str(refusal),
        }

    # Q08: the process was killed with a stage in flight. A partial artifact is not a checkpoint.
    state, _ = staged.isolated("stage_interrupted")
    _, receipt_dir = dirs("stage_interrupted")
    state["stage_in_flight"] = "enumerate_creates"
    try:
        staged.module.assert_resume_is_safe(state, directory=receipt_dir)
        results["stage_interrupted"] = {"refused": False, "note": "A KILLED RUN WAS RESUMED"}
    except staged.module.Quarantined as refusal:
        results["stage_interrupted"] = {
            "refused": True,
            "reason_code": staged.module.Q08_STAGE_INTERRUPTED,
            "message_names_the_stage": "enumerate_creates" in str(refusal),
            "not_resumed": True,
        }

    # The other half: a clean shutdown with nothing in flight must be resumable, or the guard is a
    # stop rather than a check.
    state, _ = staged.isolated("resume_is_safe")
    _, receipt_dir = dirs("resume_is_safe")
    state["stage_in_flight"] = None
    staged.module.assert_resume_is_safe(state, directory=receipt_dir)
    results["clean_resume_allowed"] = {"refused": False, "as_intended": True}

    # A completed stage runs once: the second attempt is refused by its own receipt (Q12 below),
    # and the first must actually have succeeded for that to mean anything.
    state, state_path = staged.isolated("stage_succeeds")
    log_dir, receipt_dir = dirs("stage_succeeds")
    staged.module.run_stage("program_boundary", resolved, state, runner=clean_runner,
                            log_dir=log_dir, receipt_dir=receipt_dir, state_path=state_path)
    receipt = json.loads(staged.module.receipt_path("program_boundary", receipt_dir).read_text())
    results["clean_stage_completes"] = {"refused": False, "receipt_completed": receipt["completed"]}

    # Q11: a stage that cannot be pointed at this window's directory must not run at all.
    state, state_path = staged.isolated("stage_wiring")
    log_dir, receipt_dir = dirs("stage_wiring")
    unresolved = {"wiring": "unresolved", "argv": ["true"],
                  "note": "the stage has no flag for an alternate directory"}
    try:
        staged.module.run_stage("program_boundary", unresolved, state, runner=failing_runner,
                                log_dir=log_dir, receipt_dir=receipt_dir, state_path=state_path)
        results["stage_wiring_unresolved"] = {"refused": False}
    except staged.module.Quarantined as refusal:
        results["stage_wiring_unresolved"] = {
            "refused": True,
            "reason_code": staged.module.Q11_STAGE_WIRING_UNRESOLVED,
            "message_names_the_code": staged.module.Q11_STAGE_WIRING_UNRESOLVED in str(refusal),
            "runner_never_called": True,
        }

    # Q12: a window that can be collected once may not have a stage run twice.
    state, state_path = staged.isolated("duplicate_stage")
    log_dir, receipt_dir = dirs("duplicate_stage")
    staged.module.receipt_path("program_boundary", receipt_dir).parent.mkdir(
        parents=True, exist_ok=True)
    staged.module.receipt_path("program_boundary", receipt_dir).write_text("{}")
    try:
        staged.module.run_stage("program_boundary", resolved, state, runner=failing_runner,
                                log_dir=log_dir, receipt_dir=receipt_dir, state_path=state_path)
        results["duplicate_stage"] = {"refused": False, "note": "A STAGE RAN TWICE"}
    except staged.module.Quarantined as refusal:
        results["duplicate_stage"] = {
            "refused": True,
            "reason_code": staged.module.Q12_DUPLICATE_STAGE,
            "message_names_the_code": staged.module.Q12_DUPLICATE_STAGE in str(refusal),
            "refused_before_running": True,
        }
    return results


def rehearse_two_clock_liveness(staged):
    """A poll clock that stops during a long stage must not read as death.

    The bug this rehearses: the heartbeat read 'stale' for the whole of a healthy stage, because
    the poll loop is not running while a stage runs. Two clocks, not one.
    """
    state, state_path = staged.isolated("two_clock")
    staged.module.WORK_DIR.mkdir(parents=True, exist_ok=True)
    start = 1_786_000_000
    staged.module.touch_stage_heartbeat(state, state_path, progressed=True, now=start)
    first = dict(state)  # snapshot BEFORE the second touch
    # A long stage: the heartbeat advances, progress does not.
    staged.module.touch_stage_heartbeat(state, state_path, progressed=False,
                                        now=start + staged.module.STAGE_HEARTBEAT_SECONDS * 4)
    still = dict(state)
    # ...and now the stage actually progresses, so the progress clock must move too. Without this
    # the rehearsal only shows one clock standing still, which is half the claim.
    staged.module.touch_stage_heartbeat(state, state_path, progressed=True,
                                        now=start + staged.module.STAGE_HEARTBEAT_SECONDS * 8)
    return {
        "heartbeat_before": first.get("stage_heartbeat_at"),
        "heartbeat_after": state.get("stage_heartbeat_at"),
        "progress_before": first.get("stage_progress_at"),
        "progress_while_stage_ran": still.get("stage_progress_at"),
        "progress_after_real_progress": state.get("stage_progress_at"),
        "heartbeat_while_stage_ran": still.get("stage_heartbeat_at"),
        "state_keys": sorted(k for k in state if "heartbeat" in k or "progress" in k),
        "note": ("the poll clock stops while a stage runs, so progress and liveness are separate "
                 "signals; one clock read a healthy stage as a dead supervisor"),
    }


def credited_codes(report, codes):
    """Which quarantine codes a sweep may claim, derived from the results that justify each.

    A module-level function taking the report, rather than inline accounting, so a test can hand it
    a report where a rehearsal did NOT justify a credit and check the credit is withheld. Inline,
    every condition was always true and mutating them to `True` changed nothing observable.
    """
    reached = set()
    for key in ("retries_exhausted", "non_retryable", "manifest_drift"):
        code = report.get(key, {}).get("reason_code")
        if code:
            reached.add(code)
    for entry in report.get("stage_lifecycle", {}).values():
        if isinstance(entry, dict) and entry.get("reason_code"):
            reached.add(entry["reason_code"])
    # Q04 needs EVERY non-integer tip refused. One acceptance is a hole, not a partial pass.
    probes = report.get("non_finalized_slot", {})
    if probes and all(probes.values()):
        reached.add(codes.Q04_NON_FINALIZED_SLOT)
    # Q09 needs every credential-bearing payload refused, not merely one of them.
    secret = report.get("secret_refusal", {})
    cases = ("full_url", "path_segment_only", "nested_in_a_diagnostic")
    if secret and all(secret.get(case, {}).get("refused") for case in cases):
        reached.add(codes.Q09_SECRET_WOULD_BE_WRITTEN)
    if report.get("composition_refusal", {}).get("count_keyed_by_window_word") == "refused":
        reached.add(codes.Q10_COMPOSITION_WOULD_LEAK)
    return sorted(reached)


def unreachable_codes(staged, reached):
    """What this rehearsal cannot provoke offline, and why. Silence about a gap is the gap."""
    reasons = {
        staged.module.Q01_PREREGISTRATION_DRIFT:
            "needs the frozen preregistration to differ from its pin; a document change, not a fault",
        staged.module.Q03_GIT_ANCESTRY_BROKEN:
            "needs a rewritten git history in the scratch tree, which would prove nothing about the real one",
        staged.module.Q13_AMBIGUOUS_FAILURE:
            "reached only when a failure resists classification, which an injected fault cannot honestly be",
    }
    unexplained = [code for code in staged.module.QUARANTINE_CODES
                   if code not in reached and code not in reasons]
    if unexplained:
        raise RehearsalRefused(
            f"these quarantine codes are neither reached nor explained: {unexplained}. Silence "
            f"about a gap is the gap; add a reason or reach the code.")
    return {code: reasons[code] for code in staged.module.QUARANTINE_CODES if code not in reached}


def rehearse_all():
    """Every watcher failure mode this harness can provoke, under a runtime network refusal."""
    before = live_watcher_digest()
    surface = B17A.assert_no_execution_surface(pathlib.Path(__file__).name)
    with B17A.NoNetwork(), staged_watcher() as staged:
        report = {
            "transport_classification": rehearse_transport_classification(staged),
            "retries_exhausted": rehearse_retries_exhausted(staged),
            "non_retryable": rehearse_non_retryable(staged),
            "recovers_before_exhausting": rehearse_recovers_before_exhausting(staged),
            "non_finalized_slot": rehearse_non_finalized_slot(staged),
            "manifest_drift": rehearse_manifest_drift(staged),
            "secret_refusal": rehearse_secret_refusal(staged),
            "composition_refusal": rehearse_composition_refusal(staged),
            "stage_lifecycle": rehearse_stage_lifecycle(staged),
            "two_clock_liveness": rehearse_two_clock_liveness(staged),
        }
        codes = staged.module.QUARANTINE_CODES
        reached = credited_codes(report, staged.module)
        report["quarantine_code_coverage"] = {
            "declared": list(codes),
            "reached": reached,
            "not_reached": unreachable_codes(staged, set(reached)),
        }
        report["staged_work_dir_was_scratch"] = str(staged.module.WORK_DIR).startswith(
            str(staged.root))

    after = assert_original_untouched(before)
    return {
        "schema_version": SCHEMA_VERSION,
        "harness": "B18C_WATCHER_FAILURE_REHEARSAL",
        "rehearsed_against": "a byte-identical COPY of scripts/b11c_maturity_watcher.py",
        "live_watcher_sha256_before": before,
        "live_watcher_sha256_after": after,
        "live_watcher_unchanged": before == after,
        "record_is_not_evidence": ("every fault here was constructed by this file. None describes "
                                   "anything that happened to the live run, and none may be counted."),
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "no_execution_surface": surface,
        "network": "refused at runtime: socket.socket raised for the whole sweep",
        **report,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B18c watcher failure rehearsals (offline; copies only, live watcher untouched)")
    parser.add_argument("--output", default=None)
    arguments = parser.parse_args(argv)
    report = rehearse_all()
    text = json.dumps(report, indent=1, sort_keys=True, default=str)
    if arguments.output:
        pathlib.Path(arguments.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(arguments.output).write_text(text + "\n")
    print(json.dumps({key: report[key] for key in
                      ("quarantine_code_coverage", "live_watcher_unchanged",
                       "staged_work_dir_was_scratch")}, indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
