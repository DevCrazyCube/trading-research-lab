"""B11c — durable B11a maturity watcher and frozen collection supervisor.

What this is
------------
A long-lived process that waits for the frozen B11a observation cutoff to finalize and then runs the
frozen collection stages, in order, once each, without anybody present.

Before maturity it makes exactly one kind of network call: `getSlot` at `finalized`, through B11a's
own preflight allowlist. Nothing else is reachable — not because a denylist forbids it but because
the allowlist contains one method, and every other method is refused for not being in it.

What it protects
----------------
The window is a one-shot resource. It can be burned by starting a slot early, by looking at
composition before models are frozen, by running a stage twice, by running a results stage at all,
or by writing a credential into a log that later gets pasted somewhere. Each of those has a
mechanism here rather than a promise:

- **One slot early is early.** Maturity is `tip >= cutoff` on a FINALIZED slot. A processed or
  confirmed slot can be rolled back, and a window opened on a slot that later disappears was opened
  on nothing.
- **Composition never leaves.** Counts may exist inside sealed artifacts and their own logs; the
  supervisor's state, receipts and status output carry stage names and pass/fail only.
- **A stage runs once.** Completion is a durable receipt written atomically before the next stage
  begins, so a crash between stages resumes rather than repeats — and a stage that was interrupted
  mid-flight is quarantined rather than resumed, because a partial artifact is not a checkpoint.
- **Results stages are unreachable.** The run order is checked against B11a's frozen pipeline with
  `results_unlocked=False`; `position_paths` and `outcome_labels` cannot be scheduled at all.
- **The credential never lands anywhere.** The endpoint is recorded as scheme and host only. Every
  receipt, log line and argv is scanned against the live secret before it is written, and a match
  is a fatal quarantine rather than a redaction — a redaction that fails silently looks exactly
  like one that worked.

What it is not
--------------
It does not decide anything. It does not unlock results, does not compute a label, and does not
touch B10b, B10c or B11b. U4 and U5 remain a later explicit human decision after collection.
"""
import argparse
import errno
import hashlib
import importlib.util
import json
import os
import pathlib
import shlex
import subprocess
import sys
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B11A = _load("b11a_window_freeze", "b11a_window_freeze.py")
# B11a is deliberately standalone — it imports nothing from the rest of the project, so the frozen
# window cannot be moved by an edit elsewhere. Its `WindowRefused` is therefore the base here.

SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b11a"
STATE_PATH = WORK_DIR / "supervisor_state.json"
LOCK_PATH = WORK_DIR / "supervisor.lock"
RECEIPT_DIR = WORK_DIR / "receipts"
LOG_DIR = WORK_DIR / "logs"

PID_PATH = WORK_DIR / "watcher.pid"
ARCHIVE_DIR = WORK_DIR / "superseded"

RPC_ENV_VAR = "SOLANA_RPC_URL"

# How many poll intervals a heartbeat may lag before the run is stale. Three, because one missed
# poll is a slow endpoint and three in a row is a process that is not polling.
HEARTBEAT_TOLERANCE_INTERVALS = 3

LIVENESS_ALIVE = "alive"
LIVENESS_DEAD = "dead"
LIVENESS_STALE = "stale"
LIVENESS_NOT_STARTED = "not_started"

# Conservative. The cutoff does not move, so polling faster buys nothing and only adds load.
DEFAULT_POLL_SECONDS = 300

# Bounded. A retryable failure that keeps failing is not retryable in practice, and an unbounded
# retry loop is how a watcher quietly becomes a load generator.
MAX_POLL_RETRIES = 6
BACKOFF_BASE_SECONDS = 5
BACKOFF_CAP_SECONDS = 120

STATE_INITIALISING = "initialising"
STATE_VERIFYING = "verifying"
STATE_WAITING = "waiting_for_maturity"
STATE_RUNNING_STAGE = "running_stage"
STATE_ALL_STAGES_COMPLETE = "all_stages_complete"
STATE_QUARANTINED = "quarantined"
STATES = (STATE_INITIALISING, STATE_VERIFYING, STATE_WAITING, STATE_RUNNING_STAGE,
          STATE_ALL_STAGES_COMPLETE, STATE_QUARANTINED)

Q01_PREREGISTRATION_DRIFT = "Q01_preregistration_drift"
Q02_SCRIPT_MANIFEST_DRIFT = "Q02_script_manifest_drift"
Q03_GIT_ANCESTRY_BROKEN = "Q03_git_ancestry_broken"
Q04_NON_FINALIZED_SLOT = "Q04_non_finalized_slot"
Q05_RETRIES_EXHAUSTED = "Q05_retries_exhausted"
Q06_NON_RETRYABLE_RPC = "Q06_non_retryable_rpc"
Q07_STAGE_FAILED = "Q07_stage_failed"
Q08_STAGE_INTERRUPTED = "Q08_stage_interrupted"
Q09_SECRET_WOULD_BE_WRITTEN = "Q09_secret_would_be_written"
Q10_COMPOSITION_WOULD_LEAK = "Q10_composition_would_leak"
Q11_STAGE_WIRING_UNRESOLVED = "Q11_stage_wiring_unresolved"
Q12_DUPLICATE_STAGE = "Q12_duplicate_stage"
Q13_AMBIGUOUS_FAILURE = "Q13_ambiguous_failure"
QUARANTINE_CODES = (Q01_PREREGISTRATION_DRIFT, Q02_SCRIPT_MANIFEST_DRIFT, Q03_GIT_ANCESTRY_BROKEN,
                    Q04_NON_FINALIZED_SLOT, Q05_RETRIES_EXHAUSTED, Q06_NON_RETRYABLE_RPC,
                    Q07_STAGE_FAILED, Q08_STAGE_INTERRUPTED, Q09_SECRET_WOULD_BE_WRITTEN,
                    Q10_COMPOSITION_WOULD_LEAK, Q11_STAGE_WIRING_UNRESOLVED, Q12_DUPLICATE_STAGE,
                    Q13_AMBIGUOUS_FAILURE)

# The A2 probe runs FIRST. An upgrade boundary is a property of the program, not of the window, so
# it costs no composition — and if version coverage cannot be proven there is no point collecting
# anything at all.
RUN_ORDER = ("program_boundary", "enumerate_creates", "build_cohort", "signature_inventory",
             "transaction_bodies", "decode_and_reserves", "reserve_coverage_gate",
             "failure_coverage_gate", "simulator_replay_gate")

# Stages that are not part of B11a's frozen pipeline because they touch no network and produce no
# evidence: they only reshape what an earlier stage already collected. Declared here so
# `verify_stage_order` can accept them by name rather than by exception, and asserted offline.
LOCAL_STAGES = ("build_cohort",)

# Stages that must never be schedulable here, whatever a future edit does to the order above.
FORBIDDEN_STAGES = ("position_paths", "outcome_labels")

# Everything whose bytes must be unchanged since this supervisor was written against them. A stage
# script that changed is a stage that does something else now.
MANIFEST_FILES = (
    "scripts/b11a_window_freeze.py",
    "scripts/b7d_create_enumerator.py",
    "scripts/b9c_signature_inventory.py",
    "scripts/b9d_transaction_bodies.py",
    "scripts/b9e_reserve_coverage.py",
    "scripts/b9f_failure_coverage.py",
    "scripts/b10a_simulator_kernel.py",
    "scripts/b11d_cohort_adapter.py",
    "research/pump_idl_9c82f61.json",
    "research/pump_amm_idl_9c82f61.json",
    "research/B11A_FRESH_COHORT_PREREGISTRATION.json",
    "research/B11A_FRESH_COHORT_PREREGISTRATION.md",
)

# Words that would betray composition if they reached a status line. Counts belong inside sealed
# artifacts; the supervisor publishes stage state and pass/fail.
COMPOSITION_WORDS = ("curves", "curve_count", "creates", "signatures", "transactions", "rows",
                     "trades", "mints", "population", "eligible", "count", "total")

RETRYABLE_MARKERS = ("timed out", "timeout", "temporarily unavailable", "connection reset",
                     "connection refused", "bad gateway", "service unavailable",
                     "gateway timeout", "429", "502", "503", "504", "-32005")


class WatcherRefused(B11A.WindowRefused):
    """Raised when the watcher cannot proceed without risking the window."""


class Quarantined(WatcherRefused):
    """Raised when the watcher has stopped deliberately and needs a human.

    Loud on purpose. Every condition that reaches here is one where guessing would be worse than
    stopping, and a watcher that retried its way past an ambiguous failure would be doing exactly
    the guessing this class exists to prevent.
    """


# --------------------------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------------------------

def endpoint_receipt(url):
    """Scheme and host. Never the path, never the query, never the credential.

    The configured endpoint carries its key in the query string, so anything that records a URL
    records a secret. This is the only representation allowed to leave the process.
    """
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme or not parts.hostname:
        raise WatcherRefused("the endpoint has no scheme or host to record")
    return f"{parts.scheme}://{parts.hostname}"


def _secret_values():
    """Every environment value long enough to be a credential, plus the URL's query parts."""
    values = set()
    for name, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        if any(marker in name.upper() for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD",
                                                     "AUTH")):
            values.add(value)
        if name == RPC_ENV_VAR:
            parts = urllib.parse.urlsplit(value)
            values.add(value)
            for _, candidate in urllib.parse.parse_qsl(parts.query):
                if len(candidate) >= 8:
                    values.add(candidate)
            for segment in parts.path.split("/"):
                if len(segment) >= 16:
                    values.add(segment)
    return values


def assert_no_secret(text, where):
    """A match is fatal, not redacted.

    A redaction that fails silently looks exactly like one that worked, so the only safe response
    to a secret about to be written is to stop and say where it came from.
    """
    haystack = text if isinstance(text, str) else json.dumps(text, sort_keys=True, default=str)
    for secret in _secret_values():
        if secret and secret in haystack:
            raise Quarantined(
                f"{Q09_SECRET_WOULD_BE_WRITTEN}: a credential was about to be written to {where}. "
                "Nothing is redacted here — a redaction that fails silently looks exactly like one "
                "that worked — so the write is refused and the value never leaves the process")
    return True


def assert_no_composition(payload, where):
    """Stage names and pass/fail only. Counts describing the window stay sealed.

    A composition leak is a NUMBER keyed by a word that describes the window — `{"curves": 1234}`.
    It is not the word appearing anywhere in the text: the stage `enumerate_creates` is a name, and
    refusing it would make the check fire on the pipeline's own vocabulary. So the scan looks at
    keys, and only at keys whose value is an integer.
    """
    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                if (isinstance(child, int) and not isinstance(child, bool)
                        and any(word in lowered for word in COMPOSITION_WORDS)):
                    raise Quarantined(
                        f"{Q10_COMPOSITION_WOULD_LEAK}: {path}.{key} is a number keyed by a word "
                        "that describes the window. Composition may exist inside sealed artifacts "
                        "and their own logs; the supervisor publishes stage state and pass/fail, "
                        "because a count describes the window and a description is what burns it")
                walk(child, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
    walk(payload, where)
    return True


# --------------------------------------------------------------------------------------------
# Verification before anything runs
# --------------------------------------------------------------------------------------------

def file_digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def build_manifest(files=MANIFEST_FILES):
    manifest = {}
    for relative in files:
        path = ROOT / relative
        if not path.exists():
            raise WatcherRefused(
                f"{Q02_SCRIPT_MANIFEST_DRIFT}: {relative} is missing. A pipeline cannot be started "
                "against a script that is not there")
        manifest[relative] = file_digest(path)
    return manifest


def manifest_hash(manifest):
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_preregistration(document=None):
    """The frozen document, its canonical hash, and the endpoints recomputed from the register.

    `document` is injectable so the endpoint cross-check below is reachable. With the shipped
    document it can never fire — the hash check upstream would have caught any edit — and a guard
    nothing can make fire is a guard nobody can show works.
    """
    document = B11A.load_preregistration() if document is None else document
    B11A.assert_matches_preregistration(document)
    # The endpoints are NOT re-compared here. `assert_matches_preregistration` above is exactly
    # that comparison — the document against the burned-range register — and repeating it would add
    # a second check that fires only when the first already has.
    derived = B11A.derive_window()
    return {"cutoff_slot_inclusive": derived["observation_cutoff_slot_inclusive"],
            "launch_first_slot_inclusive": derived["launch_window_first_slot_inclusive"],
            "launch_last_slot_inclusive": derived["launch_window_last_slot_inclusive"],
            # Both hashes, because they answer different questions: the file digest catches any
            # edit at all, the canonical digest catches an edit that changed the meaning rather
            # than only the whitespace. `load_preregistration` has already checked both.
            "preregistration_file_sha256": B11A.PREREGISTRATION_FILE_SHA256,
            "preregistration_canonical_sha256": B11A.PREREGISTRATION_CANONICAL_SHA256}


def verify_git_ancestry(relative="research/B11A_FRESH_COHORT_PREREGISTRATION.json", git=None):
    """The preregistration must be an ancestor of HEAD: frozen before the machinery that uses it.

    `git` is injectable so the not-an-ancestor branch can be driven. It cannot be reached with the
    real repository without rewriting history, and a branch that only fires in a situation nobody
    can construct is one nobody can test.
    """
    def run_git(*args):
        if git is not None:
            return git(*args)
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    found = run_git("log", "--diff-filter=A", "--format=%H", "--", relative).stdout.split()
    prereg = found[-1] if found else None
    if not prereg:
        raise Quarantined(
            f"{Q03_GIT_ANCESTRY_BROKEN}: the preregistration has no commit. A parameter with no "
            "history is a parameter nobody can show was frozen first")
    result = run_git("merge-base", "--is-ancestor", prereg, "HEAD")
    if result.returncode != 0:
        raise Quarantined(
            f"{Q03_GIT_ANCESTRY_BROKEN}: the preregistration commit is not an ancestor of HEAD")
    return {"preregistration_commit": prereg}


def verify_stage_order(order=RUN_ORDER):
    """Every stage is frozen, permitted before unlock, and no results stage can be scheduled.

    `order` is injectable for the same reason the two above are: with the shipped tuple every check
    here is unreachable, and an unreachable check is one nobody can show works. A test hands it a
    reordered, duplicated and results-bearing order.
    """
    known = {stage["stage"]: stage for stage in B11A.PIPELINE}
    # ONE enforcement, and it is the frozen module's own. `assert_stage_permitted` already encodes
    # both maturity and the results lock, so a local copy of either rule would be a second check
    # that fires only when this one already has. FORBIDDEN_STAGES stays as a published declaration
    # and is checked against the pipeline below — a different property.
    for name in order:
        if name in LOCAL_STAGES:
            continue
        if name not in known:
            raise WatcherRefused(
                f"{name!r} is neither a stage of the frozen pipeline nor a declared local stage")
        try:
            B11A.assert_stage_permitted(name, mature=True, results_unlocked=False)
        except B11A.WindowRefused as error:
            raise WatcherRefused(
                f"{name!r} may never be scheduled by this supervisor: {error}. U4 and U5 remain a "
                "later explicit decision and no watcher may take one") from error
    declared = tuple(stage["stage"] for stage in B11A.PIPELINE
                     if not stage["permitted_before_unlock"])
    if tuple(FORBIDDEN_STAGES) != declared:
        raise WatcherRefused(
            f"the forbidden list {list(FORBIDDEN_STAGES)} is not the frozen pipeline's results "
            f"stages {list(declared)}; a declaration that has drifted from what it describes is "
            "worse than none")
    if len(set(order)) != len(order):
        raise WatcherRefused("a stage appears twice in the run order")
    if order[0] != "program_boundary":
        raise WatcherRefused(
            "the A2 program-boundary probe must run first: it costs no composition, and if version "
            "coverage cannot be proven there is nothing worth collecting")
    return list(order)


# --------------------------------------------------------------------------------------------
# Stage wiring
# --------------------------------------------------------------------------------------------

def stage_commands(work_dir=WORK_DIR):
    """The exact argv for each stage, with every artifact path isolated under the B11a directory.

    `wiring` says whether the stage can be pointed at this directory through its own interface.
    Where it cannot, the stage is `unresolved` and the supervisor quarantines rather than running
    it — collecting a fresh window into the burned corpus's default paths, or reading the burned
    corpus as this window's population, would destroy both.
    """
    window = verify_preregistration()
    first = window["launch_first_slot_inclusive"]
    last = window["launch_last_slot_inclusive"]
    directory = pathlib.Path(work_dir)
    return {
        "program_boundary": {
            "argv": [sys.executable, "scripts/b9d_transaction_bodies.py", "collect-boundary",
                     str(directory / "b11a_program_boundary.json"), "--rpc-env", RPC_ENV_VAR],
            "wiring": "resolved",
            "note": "A2 probe; output path and RPC env are both explicit arguments",
        },
        "build_cohort": {
            "argv": [sys.executable, "scripts/b11d_cohort_adapter.py", "build",
                     "--source", str(directory / "b11a_creates.sqlite"),
                     "--output", str(directory / "b11a_cohort.sqlite")],
            "wiring": "resolved",
            "local": True,
            "note": "offline: derives the identity-and-regime cohort B9c and B9d need from the "
                    "B7d enumeration. Carries mint, bonding_curve, launch_slot and is_mayhem_mode "
                    "and nothing else; manufactures no outcome",
        },
        "enumerate_creates": {
            "argv": [sys.executable, "scripts/b7d_create_enumerator.py",
                     "--start-slot", str(first), "--end-slot", str(last + 1),
                     "--database", str(directory / "b11a_creates.sqlite"),
                     "--export-jsonl", str(directory / "b11a_creates.jsonl")],
            "wiring": "resolved",
            "note": "start, end, database and export are all explicit; end slot is exclusive",
        },
        "signature_inventory": {
            "argv": [sys.executable, "scripts/b9c_signature_inventory.py",
                     "--source", str(directory / "b11a_cohort.sqlite"),
                     "--database", str(directory / "b11a_signatures.sqlite")],
            "wiring": "resolved",
            "note": "reads the cohort artifact, whose `outcome` view answers b9c's query exactly. "
                    "Compatibility demonstrated by test rather than assumed",
        },
        "transaction_bodies": {
            "argv": [sys.executable, "scripts/b9d_transaction_bodies.py", "run",
                     str(directory / "b11a_bodies.sqlite"), "--rpc-env", RPC_ENV_VAR,
                     "--b9c", str(directory / "b11a_signatures.sqlite"),
                     "--b9a", str(directory / "b11a_cohort.sqlite")],
            "wiring": "resolved",
            "note": "the run subcommand now takes --b9c and --b9a; both name fresh paths, which "
                    "puts b9d in fresh-source mode where the burned pins and counts do not apply "
                    "and the cohort must verify itself instead",
        },
        "decode_and_reserves": {
            "argv": [sys.executable, "scripts/b9d_transaction_bodies.py", "decode",
                     str(directory / "b11a_bodies.sqlite"),
                     "--b9c", str(directory / "b11a_signatures.sqlite"),
                     "--b9a", str(directory / "b11a_cohort.sqlite")],
            "wiring": "resolved",
            "note": "decode accepts --b9c and --b9a overrides",
        },
        "reserve_coverage_gate": {
            "argv": [sys.executable, "scripts/b9e_reserve_coverage.py",
                     str(directory / "b11a_bodies.sqlite"),
                     "--b9a", str(directory / "b11a_cohort.sqlite")],
            "wiring": "resolved",
            "note": "artifact positional and --b9a override are explicit",
        },
        "failure_coverage_gate": {
            "argv": [sys.executable, "scripts/b9f_failure_coverage.py",
                     str(directory / "b11a_bodies.sqlite")],
            "wiring": "resolved",
            "note": "artifact positional is explicit",
        },
        "simulator_replay_gate": {
            "argv": [sys.executable, "scripts/b10a_simulator_kernel.py",
                     str(directory / "b11a_bodies.sqlite"), "--gate"],
            "wiring": "resolved",
            "note": "artifact positional and --gate are explicit",
        },
    }


def unresolved_stages(commands=None):
    commands = commands or stage_commands()
    return sorted(name for name in RUN_ORDER if commands[name]["wiring"] != "resolved")


# --------------------------------------------------------------------------------------------
# Durable state
# --------------------------------------------------------------------------------------------

def atomic_write_json(path, payload, where):
    """Written to a temporary file and renamed. A half-written state file is not a state."""
    assert_no_secret(payload, where)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path


def read_state(path=STATE_PATH):
    path = pathlib.Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def initial_state(window, manifest, poll_seconds):
    return {
        "schema_version": SCHEMA_VERSION,
        "state": STATE_INITIALISING,
        "cutoff_slot_inclusive": window["cutoff_slot_inclusive"],
        "preregistration_canonical_sha256": window["preregistration_canonical_sha256"],
        "manifest_sha256": manifest_hash(manifest),
        "poll_seconds": poll_seconds,
        "run_order": list(RUN_ORDER),
        "stages_completed": [],
        "stage_in_flight": None,
        "quarantine": None,
        "polls": 0,
        "last_tip_slot": None,
        "last_poll_at": None,
        "endpoint": None,
        "results_unlocked": False,
        "composition_published": False,
    }


def write_state(state, path=STATE_PATH):
    assert_no_composition(state, "supervisor state")
    return atomic_write_json(path, state, "supervisor state")


# --------------------------------------------------------------------------------------------
# Liveness
# --------------------------------------------------------------------------------------------

def process_is_this_watcher(pid):
    """Alive AND actually this watcher. A pidfile alone proves nothing.

    A PID is reused within days on a busy machine, so `kill -0` succeeding says only that SOMETHING
    is running under that number. The command line is what distinguishes our watcher from whatever
    inherited its slot.

    Matched on the SCRIPT PATH and the `--watch` flag together, not on the module name alone: a
    test runner invoked on `tests/test_b11c_maturity_watcher.py` carries that name in its own argv,
    and a liveness check that answers "yes" for the process asking the question is worse than
    none.
    """
    if not pid:
        return False
    try:
        # /proc is the authority here, and it answers both questions at once: a dead pid has no
        # entry, and a live one shows what it is actually running. A separate `os.kill(pid, 0)`
        # probe would only fire in cases this read already covers.
        cmdline = pathlib.Path(f"/proc/{int(pid)}/cmdline").read_bytes().decode("utf-8", "replace")
    except (OSError, ValueError):
        return False
    return ("scripts/b11c_maturity_watcher.py" in cmdline) and ("--watch" in cmdline)


def lock_is_held(path=LOCK_PATH):
    """Whether somebody holds the instance lock. Acquiring it means nobody does."""
    import fcntl
    path = pathlib.Path(path)
    if not path.exists():
        return False
    try:
        handle = open(path, "r+")
    except OSError:
        return False
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        handle.close()


def read_pid(path=PID_PATH):
    path = pathlib.Path(path)
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def liveness(state, pid_path=PID_PATH, lock_path=LOCK_PATH, now=None):
    """Is a watcher actually running, on three independent signals.

    A stored state of `waiting_for_maturity` says what the process was doing when it last wrote,
    not that it is still doing it. Reporting the stored value as current is how a supervisor that
    died on Tuesday still says "waiting" on Friday.
    """
    now = int(time.time()) if now is None else now
    if state is None:
        return {"liveness": LIVENESS_NOT_STARTED, "pid": None, "pid_alive": False,
                "lock_held": False, "heartbeat_age_seconds": None, "heartbeat_fresh": False}
    pid = read_pid(pid_path)
    alive = process_is_this_watcher(pid)
    held = lock_is_held(lock_path)
    last = state.get("last_poll_at")
    interval = state.get("poll_seconds") or DEFAULT_POLL_SECONDS
    age = None if last is None else now - last
    fresh = age is not None and age <= interval * HEARTBEAT_TOLERANCE_INTERVALS
    if alive and held and fresh:
        verdict = LIVENESS_ALIVE
    elif not alive and not held:
        verdict = LIVENESS_DEAD
    else:
        # Some signals agree and others do not: a held lock with no heartbeat, or a live process
        # that has stopped writing. Neither is "running normally", and calling it alive would be
        # the guess this whole module exists to avoid.
        verdict = LIVENESS_STALE
    return {"liveness": verdict, "pid": pid, "pid_alive": alive, "lock_held": held,
            "heartbeat_age_seconds": age, "heartbeat_fresh": fresh,
            "heartbeat_tolerance_seconds": interval * HEARTBEAT_TOLERANCE_INTERVALS}


def archive_run(reason, work_dir=WORK_DIR, state_path=STATE_PATH, pid_path=PID_PATH,
                archive_dir=ARCHIVE_DIR, stamp=None):
    """Move a superseded run's state and pidfile aside. Never erase.

    A failed launch is evidence about how the supervisor behaves, and deleting it would remove the
    only record that it happened. Refused if any stage completed: an archived run with receipts is
    a collection somebody may still need.
    """
    done = completed_stages(pathlib.Path(work_dir) / "receipts")
    if done:
        raise WatcherRefused(
            f"refusing to archive a run with completed stages {done}; its receipts are the record "
            "of a collection that cannot be repeated")
    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    destination = pathlib.Path(archive_dir) / stamp
    destination.mkdir(parents=True, exist_ok=True)
    moved = []
    for path in (pathlib.Path(state_path), pathlib.Path(pid_path)):
        if path.exists():
            target = destination / path.name
            os.replace(path, target)
            moved.append(str(target))
    note = {"reason": reason, "archived_at": stamp, "moved": moved,
            "stages_completed": [], "composition_published": False}
    atomic_write_json(destination / "superseded.json", note, "archive note")
    return note


# --------------------------------------------------------------------------------------------
# Single instance
# --------------------------------------------------------------------------------------------

class InstanceLock:
    """An OS-level exclusive lock. Two watchers would run every stage twice.

    `flock` rather than a pidfile: a pidfile survives a kill -9 and locks nobody out, while a flock
    is released by the kernel when the holder dies.
    """

    def __init__(self, path=LOCK_PATH, pid_path=PID_PATH):
        self.path = pathlib.Path(path)
        self.pid_path = pathlib.Path(pid_path)
        self.handle = None

    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "w")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            self.handle = None
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise WatcherRefused(
                    f"another watcher already holds {self.path}. Two supervisors would run every "
                    "stage twice against a window that can only be collected once")
            raise
        self.handle.write(f"{os.getpid()}\n")
        self.handle.flush()
        # The watcher writes its OWN pidfile, under the lock it already holds. A pidfile written by
        # the launching shell can name a process that never started, or survive one that did and
        # died; this one exists only while a process that took the lock is alive to have written it.
        pathlib.Path(self.pid_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.pid_path).write_text(f"{os.getpid()}\n")
        return self

    def __exit__(self, *_exception):
        if self.handle is not None:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None
        # Removed on a clean exit so a stale pidfile never outlives the process that wrote it. A
        # crash leaves it behind, which is exactly why liveness needs three signals and not one.
        try:
            self.pid_path.unlink()
        except OSError:
            pass
        return False


# --------------------------------------------------------------------------------------------
# Polling
# --------------------------------------------------------------------------------------------

def is_retryable(message):
    lowered = str(message).lower()
    return any(marker in lowered for marker in RETRYABLE_MARKERS)


def poll_finalized_slot(url, transport=None):
    """The only network call before maturity, and it asks for a FINALIZED slot.

    A processed or confirmed slot can be rolled back. A window opened on a slot that later
    disappears was opened on nothing, so the commitment is not a parameter.
    """
    value = B11A.preflight_call(url, "getSlot", [{"commitment": "finalized"}],
                                transport=transport)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Quarantined(
            f"{Q04_NON_FINALIZED_SLOT}: the endpoint returned {value!r} for a finalized getSlot; "
            "a tip that is not a non-negative integer is not a tip")
    return value


def poll_with_backoff(url, transport=None, retries=MAX_POLL_RETRIES, sleeper=time.sleep):
    """Bounded retries with exponential backoff. Non-retryable failures quarantine immediately."""
    for attempt in range(retries):
        try:
            return poll_finalized_slot(url, transport=transport)
        except Quarantined:
            raise
        except Exception as error:                                   # noqa: BLE001 - classified
            if not is_retryable(error):
                raise Quarantined(
                    f"{Q06_NON_RETRYABLE_RPC}: {type(error).__name__}. This is not a transport "
                    "hiccup, and retrying past it would be guessing about why it failed")
            if attempt == retries - 1:
                # Raised BEFORE sleeping again: the last backoff before giving up buys nothing and
                # the sleep is observable, which is what makes this bound testable.
                raise Quarantined(
                    f"{Q05_RETRIES_EXHAUSTED}: {retries} retryable failures in a row. A retryable "
                    "failure that keeps failing is not retryable in practice")
            sleeper(min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt)))
    raise Quarantined(f"{Q05_RETRIES_EXHAUSTED}: no attempt succeeded")


# --------------------------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------------------------

def receipt_path(stage, directory=RECEIPT_DIR):
    return pathlib.Path(directory) / f"{stage}.json"


def completed_stages(directory=RECEIPT_DIR):
    """Stages with a durable completion receipt. This is what makes a resume safe."""
    directory = pathlib.Path(directory)
    if not directory.exists():
        return []
    done = []
    for stage in RUN_ORDER:
        path = receipt_path(stage, directory)
        if path.exists():
            receipt = json.loads(path.read_text())
            if receipt.get("completed") is True:
                done.append(stage)
    return done


def assert_resume_is_safe(state, directory=RECEIPT_DIR):
    """A stage interrupted mid-flight is quarantined, never resumed.

    A partial artifact is not a checkpoint. The collection scripts are resumable in their own right,
    but the supervisor cannot tell an interrupted run from a corrupted one, and guessing which is
    exactly the judgement that loses the window.
    """
    if state.get("stage_in_flight"):
        raise Quarantined(
            f"{Q08_STAGE_INTERRUPTED}: {state['stage_in_flight']!r} was in flight when the "
            "supervisor stopped. A partial artifact is not a checkpoint, and this process cannot "
            "tell an interrupted run from a corrupted one — a human decides")
    done = completed_stages(directory)
    for stage in done:
        if stage not in RUN_ORDER:
            raise Quarantined(f"{Q12_DUPLICATE_STAGE}: a receipt exists for unknown stage {stage}")
    # A true PREFIX, not merely the right order. `["simulator_replay_gate"]` is in run order and is
    # not a prefix of it: it means every earlier stage was skipped, which is a reordered pipeline
    # rather than a resumable one.
    if list(done) != list(RUN_ORDER[:len(done)]):
        raise Quarantined(
            f"{Q12_DUPLICATE_STAGE}: completed stages {done} are not a PREFIX of the run order "
            f"{list(RUN_ORDER)}. A gap means a stage was skipped, and a skipped stage in a "
            "one-shot collection is not something a resume may paper over")
    return done


def next_stage(done):
    for stage in RUN_ORDER:
        if stage not in done:
            return stage
    return None


def run_stage(stage, command, state, runner=None, log_dir=LOG_DIR, receipt_dir=RECEIPT_DIR,
              state_path=STATE_PATH):
    """Run one stage once, with a durable receipt written after it finishes."""
    if command["wiring"] != "resolved":
        raise Quarantined(
            f"{Q11_STAGE_WIRING_UNRESOLVED}: {stage!r} cannot be pointed at the B11a directory "
            f"through its own interface. {command['note']}. Running it anyway would either collect "
            "this window into the burned corpus's paths or read the burned corpus as this window's "
            "population, and both destroy an artifact that cannot be recollected")
    if receipt_path(stage, receipt_dir).exists():
        raise Quarantined(
            f"{Q12_DUPLICATE_STAGE}: {stage!r} already has a receipt. A window that can be "
            "collected once may not have a stage run twice")

    argv = list(command["argv"])
    assert_no_secret(" ".join(shlex.quote(part) for part in argv), f"{stage} argv")
    pathlib.Path(log_dir).mkdir(parents=True, exist_ok=True)
    stdout_path = pathlib.Path(log_dir) / f"{stage}.stdout.log"
    stderr_path = pathlib.Path(log_dir) / f"{stage}.stderr.log"

    state["stage_in_flight"] = stage
    state["state"] = STATE_RUNNING_STAGE
    write_state(state, state_path)

    started = int(time.time())
    if runner is None:
        with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
            result = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err, text=True)
        returncode = result.returncode
    else:
        returncode = runner(argv, stdout_path, stderr_path)
    finished = int(time.time())

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "completed": returncode == 0,
        "exit_code": returncode,
        "started_at": started,
        "finished_at": finished,
        # Argv is recorded because a stage nobody can reproduce is a stage nobody can audit; the
        # secret scan above is what makes recording it safe.
        "argv": argv,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "manifest_sha256": state["manifest_sha256"],
        "endpoint": state["endpoint"],
    }
    atomic_write_json(receipt_path(stage, receipt_dir), receipt, f"{stage} receipt")

    state["stage_in_flight"] = None
    if returncode != 0:
        state["state"] = STATE_QUARANTINED
        state["quarantine"] = {"reason_code": Q07_STAGE_FAILED, "stage": stage,
                               "exit_code": returncode}
        write_state(state, state_path)
        raise Quarantined(f"{Q07_STAGE_FAILED}: {stage!r} exited {returncode}; see "
                          f"{stderr_path}")
    state["stages_completed"] = completed_stages(receipt_dir)
    write_state(state, state_path)
    return receipt


# --------------------------------------------------------------------------------------------
# Planning and status
# --------------------------------------------------------------------------------------------

def dry_run_plan(poll_seconds=DEFAULT_POLL_SECONDS, work_dir=WORK_DIR):
    """Everything the watcher would do, computed offline. No network, no execution."""
    window = verify_preregistration()
    manifest = build_manifest()
    order = verify_stage_order()
    commands = stage_commands(work_dir)
    unresolved = unresolved_stages(commands)
    plan = {
        "schema_version": SCHEMA_VERSION,
        "cutoff_slot_inclusive": window["cutoff_slot_inclusive"],
        "preregistration_canonical_sha256": window["preregistration_canonical_sha256"],
        "manifest_sha256": manifest_hash(manifest),
        "manifest_files": len(manifest),
        "poll_seconds": poll_seconds,
        "preflight_methods": list(B11A.PREFLIGHT_ALLOWED_METHODS),
        "commitment": "finalized",
        "run_order": order,
        "forbidden_stages": list(FORBIDDEN_STAGES),
        "results_unlocked": False,
        "stages": [{"stage": name, "wiring": commands[name]["wiring"],
                    "note": commands[name]["note"],
                    "argv": " ".join(shlex.quote(part) for part in commands[name]["argv"])}
                   for name in order],
        "stages_unresolved": unresolved,
        "launch_ready_for_collection": not unresolved,
        "quarantine_codes": list(QUARANTINE_CODES),
        "composition_published": False,
    }
    assert_no_secret(plan, "dry-run plan")
    return plan


def status(state_path=STATE_PATH, receipt_dir=RECEIPT_DIR, pid_path=PID_PATH,
           lock_path=LOCK_PATH):
    """What an operator may see. Stage state and pass/fail; never a count."""
    state = read_state(state_path)
    signals = liveness(state, pid_path, lock_path)
    if state is None:
        return {"state": LIVENESS_NOT_STARTED, "liveness": LIVENESS_NOT_STARTED,
                "reported_state": None, "composition_published": False, **signals}
    done = completed_stages(receipt_dir)
    view = {
        # What is TRUE NOW. The stored value is what the process was doing when it last wrote, and
        # publishing that as current is how a supervisor that died on Tuesday still says "waiting"
        # on Friday.
        "state": state["state"] if signals["liveness"] == LIVENESS_ALIVE else signals["liveness"],
        "reported_state": state["state"],
        "cutoff_slot_inclusive": state["cutoff_slot_inclusive"],
        "last_tip_slot": state["last_tip_slot"],
        "slots_remaining": (None if state["last_tip_slot"] is None
                            else max(0, state["cutoff_slot_inclusive"] - state["last_tip_slot"])),
        "polls": state["polls"],
        "last_poll_at": state["last_poll_at"],
        "endpoint": state["endpoint"],
        "stages_completed": done,
        "stages_remaining": [s for s in RUN_ORDER if s not in done],
        "stage_in_flight": state["stage_in_flight"],
        "quarantine": state["quarantine"],
        "results_unlocked": False,
        "composition_published": False,
        **signals,
    }
    assert_no_composition(state, "the state behind status")
    assert_no_secret(view, "status")
    return view


# --------------------------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------------------------

def watch(url, poll_seconds=DEFAULT_POLL_SECONDS, transport=None, sleeper=time.sleep,
          runner=None, max_iterations=None, work_dir=WORK_DIR, state_path=STATE_PATH,
          receipt_dir=RECEIPT_DIR, log_dir=LOG_DIR, commands=None):
    """Verify, wait for a finalized cutoff, then run the frozen stages once each."""
    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    window = verify_preregistration()
    manifest = build_manifest()
    verify_git_ancestry()
    verify_stage_order()
    # Injectable so the whole state machine can be exercised against a fake command set. In the
    # real run this is the wiring computed from the frozen window, and an unresolved stage in it
    # quarantines rather than running.
    commands = commands if commands is not None else stage_commands(work_dir)

    state = read_state(state_path) or initial_state(window, manifest, poll_seconds)
    if state.get("state") == STATE_QUARANTINED:
        raise Quarantined(f"the watcher is quarantined: {state.get('quarantine')}")
    # Reverified on every start, not only the first: a manifest checked once is a manifest that
    # stopped being checked.
    if state["manifest_sha256"] != manifest_hash(manifest):
        state["state"] = STATE_QUARANTINED
        state["quarantine"] = {"reason_code": Q02_SCRIPT_MANIFEST_DRIFT}
        write_state(state, state_path)
        raise Quarantined(
            f"{Q02_SCRIPT_MANIFEST_DRIFT}: a stage script, IDL or the preregistration changed since "
            "this run began. A stage script that changed is a stage that does something else now")
    if state["preregistration_canonical_sha256"] != window["preregistration_canonical_sha256"]:
        state["state"] = STATE_QUARANTINED
        state["quarantine"] = {"reason_code": Q01_PREREGISTRATION_DRIFT}
        write_state(state, state_path)
        raise Quarantined(f"{Q01_PREREGISTRATION_DRIFT}: the frozen document changed under the run")

    state["endpoint"] = endpoint_receipt(url)
    state["state"] = STATE_VERIFYING
    write_state(state, state_path)
    done = assert_resume_is_safe(state, receipt_dir)
    state["stages_completed"] = done

    iterations = 0
    while True:
        if max_iterations is not None and iterations >= max_iterations:
            return state
        iterations += 1

        tip = poll_with_backoff(url, transport=transport, sleeper=sleeper)
        state["polls"] += 1
        state["last_tip_slot"] = tip
        state["last_poll_at"] = int(time.time())
        verdict = B11A.maturity(tip)
        if not verdict["mature"]:
            state["state"] = STATE_WAITING
            write_state(state, state_path)
            sleeper(poll_seconds)
            continue

        state["state"] = STATE_RUNNING_STAGE
        write_state(state, state_path)
        while True:
            stage = next_stage(state["stages_completed"])
            if stage is None:
                state["state"] = STATE_ALL_STAGES_COMPLETE
                write_state(state, state_path)
                return state
            run_stage(stage, commands[stage], state, runner=runner, log_dir=log_dir,
                      receipt_dir=receipt_dir, state_path=state_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="offline plan; no network")
    parser.add_argument("--verify", action="store_true", help="offline verification only")
    parser.add_argument("--status", action="store_true", help="redacted operator status")
    parser.add_argument("--watch", action="store_true", help="run the watcher")
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--max-iterations", type=int, default=None)
    args = parser.parse_args(argv)

    if args.dry_run:
        print(json.dumps(dry_run_plan(args.poll_seconds), indent=2, sort_keys=True))
        return 0
    if args.verify:
        window = verify_preregistration()
        manifest = build_manifest()
        report = {"preregistration": window, "manifest_sha256": manifest_hash(manifest),
                  "manifest_files": len(manifest), "git": verify_git_ancestry(),
                  "run_order": verify_stage_order(),
                  "stages_unresolved": unresolved_stages(),
                  "preflight_methods": list(B11A.PREFLIGHT_ALLOWED_METHODS)}
        assert_no_secret(report, "verify report")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    if args.watch:
        url = os.environ.get(RPC_ENV_VAR)
        if not url:
            raise WatcherRefused(
                f"{RPC_ENV_VAR} is not set. Credentials are environment-only and this process "
                "never reads one from a file it wrote")
        with InstanceLock():
            state = watch(url, poll_seconds=args.poll_seconds,
                          max_iterations=args.max_iterations)
        print(json.dumps({"state": state["state"], "polls": state["polls"],
                          "composition_published": False}, indent=2, sort_keys=True))
        return 0
    parser.error("choose one of --dry-run, --verify, --status or --watch")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B11A.WindowRefused as error:
        print(f"WatcherRefused: {error}", file=sys.stderr)
        sys.exit(2)
