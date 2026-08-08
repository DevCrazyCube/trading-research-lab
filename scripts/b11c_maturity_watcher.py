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
import urllib.error
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B11A = _load("b11a_window_freeze", "b11a_window_freeze.py")
# The shared transport classification. Loaded, not reimplemented: two copies of a retry policy
# drift, and the drift is what killed a run.
HTTP = _load("rpc_http_identity", "rpc_http_identity.py")
# B11a is deliberately standalone — it imports nothing from the rest of the project, so the frozen
# window cannot be moved by an edit elsewhere. Its `WindowRefused` is therefore the base here.

SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b11a"
STATE_PATH = WORK_DIR / "supervisor_state.json"
LOCK_PATH = WORK_DIR / "supervisor.lock"
RECEIPT_DIR = WORK_DIR / "receipts"
LOG_DIR = WORK_DIR / "logs"

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

# While a stage runs the poll clock stops, so the supervisor proves it is alive on this cadence
# instead. Short relative to a stage measured in hours, and cheap: one small atomic state write.
STAGE_HEARTBEAT_SECONDS = 30

# How long a stage may produce nothing before its PROGRESS is reported as stalled. This is not a
# timeout and kills nothing -- a legitimately quiet stage exists -- it is what makes a hung child
# visible to an operator instead of hidden behind a faithful supervisor heartbeat.
STAGE_PROGRESS_TOLERANCE_SECONDS = 900

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
RUN_ORDER = ("program_boundary", "enumerate_creates", "build_cohort", "subsample_cohort",
             "signature_inventory",
             "transaction_bodies", "decode_and_reserves", "reserve_coverage_gate",
             "failure_coverage_gate", "simulator_replay_gate")

# Stages that are not part of B11a's frozen pipeline because they touch no network and produce no
# evidence: they only reshape what an earlier stage already collected. Declared here so
# `verify_stage_order` can accept them by name rather than by exception, and asserted offline.
LOCAL_STAGES = ("build_cohort", "subsample_cohort")

# Stages that must never be schedulable here, whatever a future edit does to the order above.
FORBIDDEN_STAGES = ("position_paths", "outcome_labels")

# Stage 5's parallelism, MEASURED against this endpoint rather than chosen. Named here instead of
# written into the argv because a bare 4 beside a URL is a number the next reader has to
# reverse-engineer, and the reasoning is the useful part:
#
#   1 worker   5.85 calls/s   p50 171ms      2 workers  10.42 calls/s   p50 183ms
#   4 workers 13.76 calls/s   p50 247ms      8 workers  15.71 calls/s   p50 473ms
#
# 197 read-only getTransaction calls against real create signatures, through the shared transport
# identity, aborting on the first 429. There were none at any level -- so this is NOT the provider's
# refusal point, it is the knee before it. Eight workers buy fourteen percent more throughput than
# four while p50 latency nearly doubles, which is the provider QUEUEING our calls rather than
# serving them faster, and this credential has previously been 429'd on every call including ones it
# had already served. Paying a lot of provider pressure for a little throughput is the wrong side of
# that trade, so the cap is the knee and not the ceiling.
#
# (The phrasing above avoids one particular word on purpose: this module is held to making no
# network call of its own by a TEXT SCAN over its own source, and prose in a comment counts. The
# scan is deliberately blunt and reworded prose is the cheaper side of that trade.)
#
# Worth knowing for anyone tempted to raise --calls-per-second instead: they would be turning a knob
# that does nothing. The collector is serial at workers=1, so it is LATENCY-bound at ~5.8/s and any
# ceiling above that never binds. Parallelism is the lever; the rate is only the cap on it.
TRANSACTION_BODY_WORKERS = 4

# The preregistered draw size, frozen in B11F_COHORT_SUBSAMPLE_PREREGISTRATION and repeated here
# only so the argv can carry it. The SEED is NOT repeated: it lives in the selector as a frozen
# constant, because a value on a command line is one an operator can change without amending the
# document that froze it, and the whole point of the draw is that it was chosen in ignorance.
SUBSAMPLE_N = 5000

# Everything whose bytes must be unchanged since this supervisor was written against them. A stage
# script that changed is a stage that does something else now.
MANIFEST_FILES = (
    # This supervisor pins ITSELF. It attests the manifest, then waits days, then reads disk again at
    # the maturity transition and launches the stages. An edit to this file during that wait would
    # change which stages run, in what order, and under which gates -- the very substitution the
    # manifest exists to prevent -- and until it was listed here that one file was the blind spot.
    # A process whose own code changed under it must quarantine, not proceed.
    "scripts/b11c_maturity_watcher.py",
    "scripts/b11a_window_freeze.py",
    # The shared client identity every stage transport loads. Pinned here because a manifest that
    # attests the four transports but not the one module they all send through would have a hole
    # exactly the size of the thing that talks to the network.
    #
    # Named as data, not imported: this supervisor still makes no call of its own, and the text scan
    # in `test_the_module_makes_no_call_outside_the_preflight` is what holds that.
    "scripts/rpc_http_identity.py",
    "scripts/b7d_create_enumerator.py",
    "scripts/b9c_signature_inventory.py",
    "scripts/b9d_transaction_bodies.py",
    "scripts/b9e_reserve_coverage.py",
    "scripts/b9f_failure_coverage.py",
    "scripts/b10a_simulator_kernel.py",
    "scripts/b11d_cohort_adapter.py",
    # The subsample selector. Pinned because it decides WHICH curves are studied, which makes it
    # the most selection-critical file the pipeline runs -- an edit here during the wait would
    # change the population under a preregistration frozen precisely to stop that. It was missing
    # from this list when `subsample_cohort` was first wired, and nothing noticed: every other
    # stage script was pinned, so the gap was one name rather than a category. The test below now
    # derives the requirement from the stage table instead of from anyone remembering.
    "scripts/b11f_cohort_subsample.py",
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

# RPC-level refusals that no retry can lift, checked BEFORE the retryable markers. -32002 is the
# provider answering that this plan may not ask -- an answer about who you are, not about now.
NON_RETRYABLE_RPC_MARKERS = ("-32002",)


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
    try:
        return HTTP.assert_endpoint_identity_is_safe(url)
    except HTTP.TransportIdentityError as error:
        raise WatcherRefused(f"the endpoint cannot be recorded safely: {error}") from error


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


def assert_manifest_unchanged(state, state_path, manifest=None):
    """The pinned scripts must still be the pinned scripts. Checked whenever it could have changed.

    Called at start AND again the instant maturity arrives, because those are different moments and
    the gap between them is the whole point. A run attests its manifest, then waits — here, on the
    order of days — and only then executes the stages, as subprocesses that read whatever is on
    disk at that moment. Verifying once before the wait attests the scripts that were there when
    the waiting started, not the ones that end up running. Any edit landing during the wait would
    have been collected under, and attested away by, a digest describing different code: exactly
    the provenance lie the manifest exists to prevent, on the only path where it matters.
    """
    manifest = build_manifest() if manifest is None else manifest
    if state["manifest_sha256"] == manifest_hash(manifest):
        return manifest
    state["state"] = STATE_QUARANTINED
    state["quarantine"] = {"reason_code": Q02_SCRIPT_MANIFEST_DRIFT}
    write_state(state, state_path)
    raise Quarantined(
        f"{Q02_SCRIPT_MANIFEST_DRIFT}: a stage script, IDL or the preregistration changed since "
        "this run began. A stage script that changed is a stage that does something else now")


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
                     str(directory / "b11a_bodies.sqlite"), "--rpc-env", RPC_ENV_VAR,
                     "--cutoff-slot", str(window["cutoff_slot_inclusive"])],
            "wiring": "resolved",
            "note": "A2 probe, writing INTO the bodies artifact rather than beside it. It used to "
                    "write b11a_program_boundary.json, and nothing ever read that file: `decode` "
                    "takes its boundary evidence from the artifact it is decoding, via "
                    "`verify_artifact(database)` -> `assert_boundary_evidence_complete`, and stage "
                    "5 never puts boundary rows there. So stage 6 would have failed on "
                    "'boundary_completed_at_unix is absent' after stage 5's days of collection. "
                    "The name was also a lie about the file -- `collect-boundary` writes a full "
                    "b9d SQLite artifact, ten tables, and the .json suffix meant b11e's "
                    "'writes X which nothing reads' check skipped it by extension",
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
        "subsample_cohort": {
            "argv": [sys.executable, "scripts/b11f_cohort_subsample.py", "build",
                     "--source", str(directory / "b11a_cohort.sqlite"),
                     "--output", str(directory / "b11a_subsample.sqlite"),
                     "--n", str(SUBSAMPLE_N)],
            "wiring": "resolved",
            "local": True,
            "note": "offline: draws the preregistered subsample from the full cohort. Local for "
                    "the same reason build_cohort is -- no network, no evidence, it only reshapes "
                    "what an earlier stage already collected. It exists because the full 33,866 "
                    "curves are ~43M in-window signatures, about 36 days of stage 5 at the "
                    "measured concurrent rate; the draw is hash-on-mint, uniform, and frozen in "
                    "B11F before any outcome existed. The SEED is the selector's own frozen "
                    "constant and is deliberately NOT passed here: a seed on the command line is "
                    "a seed somebody can change without amending the preregistration",
        },
        "signature_inventory": {
            "argv": [sys.executable, "scripts/b9c_signature_inventory.py",
                     "--source", str(directory / "b11a_subsample.sqlite"),
                     "--database", str(directory / "b11a_signatures.sqlite"),
                     "--creates", str(directory / "b11a_creates.sqlite"),
                     "--cutoff-slot", str(window["cutoff_slot_inclusive"])],
            "wiring": "resolved",
            "note": "reads the cohort artifact, whose `outcome` view answers b9c's query exactly. "
                    "Compatibility was demonstrated by test rather than assumed -- but the test "
                    "demonstrated the QUERY SHAPE, and b9c also carried EXPECTED_MEMBERS = 1601 "
                    "and CUTOFF_TIME, both describing the B9 study. The count refused this "
                    "window's 33,866-member cohort in one second after three days of collection. "
                    "The horizon would NOT have refused: it is consulted through a bracket that "
                    "any window starting before 27 Jul 14:19 satisfies, so such a window would "
                    "have truncated itself at another study's clock silently. b9c now splits "
                    "burned from fresh and REQUIRES the horizon; the slot comes from "
                    "`verify_preregistration` above, which runs the Q01 hash gate before "
                    "returning it, so a document that drifted mid-run refuses here rather than "
                    "handing a stale bound to a collection. --creates lets the fresh population "
                    "be checked against the enumeration it was built from, since the pin cannot",
        },
        "transaction_bodies": {
            "argv": [sys.executable, "scripts/b9d_transaction_bodies.py", "run",
                     str(directory / "b11a_bodies.sqlite"), "--rpc-env", RPC_ENV_VAR,
                     "--b9c", str(directory / "b11a_signatures.sqlite"),
                     "--b9a", str(directory / "b11a_subsample.sqlite"),
                     "--cutoff-slot", str(window["cutoff_slot_inclusive"]),
                     "--workers", str(TRANSACTION_BODY_WORKERS)],
            "wiring": "resolved",
            "note": "the run subcommand now takes --b9c and --b9a; both name fresh paths, which "
                    "puts b9d in fresh-source mode where the burned pins and counts do not apply "
                    "and the cohort must verify itself instead. --cutoff-slot because fresh mode "
                    "was NOT in fact free of the burned horizon: `initialize_run` stamps b9d's own "
                    "CUTOFF_SLOT = 435,536,742 into this artifact's metadata under a drift check, "
                    "and B11a's window sits entirely above that slot",
        },
        "decode_and_reserves": {
            "argv": [sys.executable, "scripts/b9d_transaction_bodies.py", "decode",
                     str(directory / "b11a_bodies.sqlite"),
                     "--b9c", str(directory / "b11a_signatures.sqlite"),
                     "--b9a", str(directory / "b11a_subsample.sqlite")],
            "wiring": "resolved",
            "note": "decode accepts --b9c and --b9a overrides, and DELIBERATELY takes no horizon. "
                    "It needs one -- this is the stage the burned range would have stopped, since "
                    "`program_version_rows` measured intervals against OBSERVATION_RANGE on both "
                    "ends -- but it reads that horizon from the artifact's own metadata rather "
                    "than from argv. That is not the artifact vouching for itself: the cutoff is "
                    "stamped by `transaction_bodies` and the intervals are minted by "
                    "`program_boundary`, two different stages, so agreement between them is "
                    "evidence. Passing it a fourth time here would add a bound nobody checks "
                    "against the two that are already cross-checked",
        },
        "reserve_coverage_gate": {
            "argv": [sys.executable, "scripts/b9e_reserve_coverage.py",
                     str(directory / "b11a_bodies.sqlite"),
                     "--b9a", str(directory / "b11a_subsample.sqlite")],
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
        "stage_pid": None,
        "stage_heartbeat_at": None,
        "stage_progress_at": None,
        "stage_output_bytes": None,
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


def read_pid(lock_path=LOCK_PATH):
    """The pid recorded in the lock file by whoever holds it.

    The lock file is the record. A stale pid can outlive its process — the file is not removed on
    exit — which is exactly why liveness pairs it with the flock and the heartbeat rather than
    trusting it alone.
    """
    path = pathlib.Path(lock_path)
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def liveness(state, lock_path=LOCK_PATH, now=None):
    """Is a watcher actually running, on three independent signals.

    A stored state of `waiting_for_maturity` says what the process was doing when it last wrote,
    not that it is still doing it. Reporting the stored value as current is how a supervisor that
    died on Tuesday still says "waiting" on Friday.
    """
    now = int(time.time()) if now is None else now
    if state is None:
        return {"liveness": LIVENESS_NOT_STARTED, "pid": None, "pid_alive": False,
                "lock_held": False, "heartbeat_age_seconds": None, "heartbeat_fresh": False}
    pid = read_pid(lock_path)
    alive = process_is_this_watcher(pid)
    held = lock_is_held(lock_path)
    # WHICH heartbeat depends on what the supervisor is doing, because the poll clock stops the
    # moment a stage starts. Judging a running stage by `last_poll_at` reported `stale` for an
    # entire healthy 40-hour stage and masked `running_stage` in the operator's view -- so the
    # signal was useless exactly while collection was happening, which is when it matters most.
    running = state.get("state") == STATE_RUNNING_STAGE
    if running:
        source = "stage"
        last = state.get("stage_heartbeat_at")
        interval = STAGE_HEARTBEAT_SECONDS
    else:
        source = "poll"
        last = state.get("last_poll_at")
        interval = state.get("poll_seconds") or DEFAULT_POLL_SECONDS
    tolerance = interval * HEARTBEAT_TOLERANCE_INTERVALS
    age = None if last is None else now - last
    fresh = age is not None and age <= tolerance
    if alive and held and fresh:
        verdict = LIVENESS_ALIVE
    elif not alive and not held:
        verdict = LIVENESS_DEAD
    else:
        # Some signals agree and others do not: a held lock with no heartbeat, or a live process
        # that has stopped writing. Neither is "running normally", and calling it alive would be
        # the guess this whole module exists to avoid.
        verdict = LIVENESS_STALE
    signals = {"liveness": verdict, "pid": pid, "pid_alive": alive, "lock_held": held,
               "heartbeat_age_seconds": age, "heartbeat_fresh": fresh,
               "heartbeat_source": source, "heartbeat_tolerance_seconds": tolerance}
    if running:
        # A live supervisor faithfully writing heartbeats while its CHILD hangs would read as
        # healthy, so the stage's own progress is reported separately. Supervisor liveness and stage
        # progress are different questions and conflating them is what hid the last defect.
        progress = state.get("stage_progress_at")
        signals["stage_pid"] = state.get("stage_pid")
        signals["stage_progress_age_seconds"] = None if progress is None else now - progress
        signals["stage_progressing"] = (
            progress is not None and now - progress <= STAGE_PROGRESS_TOLERANCE_SECONDS)
    return signals


INCIDENT_DIR = WORK_DIR / "incidents"

# A directory name nobody can mistake for a resumable run, and a marker file that says so inside it.
INCIDENT_MARKER = "INVALIDATED_DO_NOT_RESUME.json"


def incident_quarantine(reason_code, reason, secret_bearing, work_dir=WORK_DIR,
                        state_path=STATE_PATH, lock_path=LOCK_PATH, receipt_dir=RECEIPT_DIR,
                        log_dir=LOG_DIR, incident_dir=INCIDENT_DIR, stamp=None,
                        secret_values=None):
    """Retire a run that produced UNUSABLE evidence, deliberately unlike `archive_run`.

    `archive_run` exists for a run that never collected anything and REFUSES once a receipt exists,
    which is right: a run holding receipts describes a collection somebody may still need. An
    incident is the other case -- receipts exist AND the evidence must not be reused -- so it needs
    its own procedure rather than a flag on the normal one. Two paths that differ only in a boolean
    are two paths one careless call can confuse.

    What it does, in this order:

    1. Captures forensics for EVERY file first, including the ones about to be removed: relative
       path, byte size and sha256. A hash recorded after deletion is a hash of nothing.
    2. Moves the clean, credential-free evidence aside -- state, lock, receipts, logs -- so the
       record of what happened survives.
    3. REMOVES the files named in `secret_bearing`, and only those, after their hashes are captured.
       They are the one class of artifact that must not be retained, because retaining a credential
       is the harm.
    4. Writes `INVALIDATED_DO_NOT_RESUME.json` into the incident directory. The directory is not
       under `superseded/`, so nothing that walks archived runs will offer it as a resume.

    `secret_values` is injectable so the scan can be driven in a test without a live credential; it
    defaults to the live ones. The report itself is scanned before it is written, and a match refuses
    rather than redacts -- the same stance as everywhere else here.
    """
    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    work_dir = pathlib.Path(work_dir)
    destination = pathlib.Path(incident_dir) / stamp
    destination.mkdir(parents=True, exist_ok=True)
    values = _secret_values() if secret_values is None else set(secret_values)
    forbidden = {str(pathlib.Path(p)) for p in secret_bearing}

    def forensics(path):
        blob = path.read_bytes()
        return {"path": str(path.relative_to(work_dir)), "size_bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
                "credential_present": any(v and v.encode() in blob for v in values)}

    captured, removed, preserved = [], [], []
    for path in sorted(work_dir.rglob("*")):
        if path.is_dir() or INCIDENT_DIR.name in path.parts or ARCHIVE_DIR.name in path.parts:
            continue
        record = forensics(path)
        captured.append(record)
        if str(path) in forbidden or record["credential_present"]:
            path.unlink()
            removed.append(record)
        else:
            target = destination / path.relative_to(work_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
            preserved.append(record)

    report = {
        "schema_version": SCHEMA_VERSION,
        "incident_at": stamp,
        "reason_code": reason_code,
        "reason": reason,
        "not_for_resume": ("This run's evidence is INVALIDATED. A clean rerun must start from zero "
                           "receipts and regenerate every stage. Nothing here may be reused, "
                           "resumed from, or smoothed into a later run."),
        "removed_because_credential_bearing": removed,
        "preserved_credential_free": preserved,
        "files_examined": len(captured),
        "endpoint_value_never_recorded": ("only the offending metadata KEY name is recorded; the "
                                          "endpoint value and its path are not written here"),
    }
    # Scanned against the SAME values used to classify the files, not only the live environment.
    # Scanning solely via `assert_no_secret` made this guard undrivable whenever the suite ran
    # without the credential exported, which is most of the time -- and a guard that cannot be
    # driven is one nobody has shown works.
    serialized = json.dumps(report, sort_keys=True, default=str)
    leaked = sorted(v for v in values if v and v in serialized)
    if leaked:
        raise Quarantined(
            f"{Q09_SECRET_WOULD_BE_WRITTEN}: the incident report would carry credential material. "
            f"Nothing is redacted here, so the write is refused and the incident directory is left "
            f"without a marker rather than with a leaking one")
    assert_no_secret(report, "the incident report")
    atomic_write_json(destination / INCIDENT_MARKER, report, "incident report")
    return report


def archive_run(reason, work_dir=WORK_DIR, state_path=STATE_PATH, lock_path=LOCK_PATH,
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
    for path in (pathlib.Path(state_path), pathlib.Path(lock_path)):
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

    def __init__(self, path=LOCK_PATH):
        self.path = pathlib.Path(path)
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
        # The pid goes in the LOCK FILE, not a second file beside it. One artifact, written under
        # the lock by the process that holds it, so the pid and the lock can never disagree — and
        # there is no separate path to get wrong.
        #
        # There WAS one, and it was wrong: `pid_path` defaulted to the module-level PID_PATH, which
        # Python binds at import time, so a test passing only a temporary LOCK path still wrote to
        # and then deleted the real watcher's pidfile. Rebinding the module global did not even
        # help. The fix is to have no second path at all.
        self.handle.write(f"{os.getpid()}\n")
        self.handle.flush()
        return self

    def __exit__(self, *_exception):
        if self.handle is not None:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None
        return False


# --------------------------------------------------------------------------------------------
# Polling
# --------------------------------------------------------------------------------------------

def supersede_stages(names, reason, work_dir=WORK_DIR, state_path=STATE_PATH,
                     archive_dir=ARCHIVE_DIR, lock_path=LOCK_PATH, receipt_dir=RECEIPT_DIR,
                     artifacts=(), stamp=None, clear_quarantine=False):
    """Retire named stages so they will run again. Explicit, recorded, and never destructive.

    `archive_run` cannot do this: it refuses the moment any stage has a receipt, because an
    archived run with receipts is a collection somebody may still need. That is the right rule for
    a failed launch and the wrong tool for a partial run whose EARLY stages must be redone. B11a is
    the case — stage 1 collected an upgrade-boundary proof for slots 433,894,233..435,536,742, and
    the window it will be used against begins 32,408 slots above that. The evidence is not stale,
    it is about somewhere else.

    THE PREFIX RULE IS ENFORCED HERE RATHER THAN DISCOVERED AT RESUME, and that is the whole
    reason this is a function instead of four `mv` commands. `assert_resume_is_safe` requires the
    completed stages to be a true PREFIX of the run order, so superseding stage 1 while stages 2
    and 3 keep their receipts leaves a HOLE, and the supervisor cannot tell a hole made on purpose
    from a stage that was skipped — nor should it learn to guess, since guessing wrong green-lights
    a gap in a collection that cannot be repeated. Refusing here means the operator finds out
    BEFORE the evidence has been moved, rather than at the next start with the receipts already
    somewhere else.

    Never deletes. Everything moves under `superseded/<stamp>/` beside a note recording what was
    moved, why, and the state at the time — including the quarantine verbatim when one is cleared.
    A supersede whose reason is unrecoverable later is a supersede nobody can audit.
    """
    if not names:
        raise WatcherRefused("superseding nothing is not an operation; name the stages")
    unknown = [name for name in names if name not in RUN_ORDER]
    if unknown:
        raise WatcherRefused(
            f"unknown stage(s) {unknown}; the run order is {list(RUN_ORDER)}")
    duplicates = sorted({name for name in names if list(names).count(name) > 1})
    if duplicates:
        raise WatcherRefused(f"stage(s) {duplicates} named twice; say once what you mean once")
    if not (reason or "").strip():
        raise WatcherRefused(
            "a supersede without a reason cannot be audited afterwards; state why")
    if lock_is_held(lock_path):
        raise WatcherRefused(
            "the instance lock is held, so a supervisor is alive. Moving receipts out from under a "
            "running collection is how two processes come to disagree about what has been done")

    work_dir = pathlib.Path(work_dir)
    receipt_dir = pathlib.Path(receipt_dir)
    before = completed_stages(receipt_dir)

    missing = [name for name in names if not receipt_path(name, receipt_dir).exists()]
    if missing:
        raise WatcherRefused(
            f"no receipt for stage(s) {missing}; superseding something that is not there means the "
            "plan and the artifact tree disagree, and the tree is the record")

    remaining = [stage for stage in before if stage not in names]
    if list(remaining) != list(RUN_ORDER[:len(remaining)]):
        raise WatcherRefused(
            f"superseding {sorted(names)} would leave completed stages {remaining}, which is not a "
            f"PREFIX of {list(RUN_ORDER)}. A resume would quarantine on {Q12_DUPLICATE_STAGE} "
            "because a hole is indistinguishable from a skipped stage. Supersede the stages after "
            "it as well, so what remains is a prefix")

    resolved = []
    for artifact in artifacts:
        path = pathlib.Path(artifact)
        path = path if path.is_absolute() else work_dir / path
        # `resolve` before comparing: a relative escape like ../../scripts would otherwise pass a
        # textual check and move a file out of a directory this function has no business leaving.
        if work_dir.resolve() not in path.resolve().parents:
            raise WatcherRefused(
                f"{artifact} is outside {work_dir}; this moves a collection's own artifacts and "
                "nothing else")
        if not path.exists():
            raise WatcherRefused(f"no artifact at {path}; refusing to record a move that cannot "
                                 "have happened")
        resolved.append(path)

    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    destination = pathlib.Path(archive_dir) / stamp
    if destination.exists():
        raise WatcherRefused(
            f"{destination} already exists; writing a second supersede into one archive would "
            "leave two records claiming to be the same moment")

    state = read_state(state_path) or {}
    quarantine = state.get("quarantine")
    if quarantine and not clear_quarantine:
        raise WatcherRefused(
            f"the watcher is quarantined ({quarantine.get('reason_code')}) and clear_quarantine "
            "was not requested. Superseding the receipts without clearing it leaves a run that "
            "cannot start for a reason that no longer applies; clearing it silently would erase "
            "why the collection stopped. Ask for it explicitly and it is recorded")

    (destination / "receipts").mkdir(parents=True)
    moved = []
    for name in names:
        source = receipt_path(name, receipt_dir)
        target = destination / "receipts" / source.name
        os.replace(source, target)
        moved.append({"stage": name, "from": str(source), "to": str(target)})
    if resolved:
        (destination / "artifacts").mkdir()
        for path in resolved:
            target = destination / "artifacts" / path.name
            os.replace(path, target)
            moved.append({"stage": None, "from": str(path), "to": str(target)})

    after = completed_stages(receipt_dir)
    note = {
        "reason": reason,
        "archived_at": stamp,
        "superseded_stages": list(names),
        "moved": moved,
        "stages_completed_before": before,
        "stages_completed_after": after,
        # Verbatim, because this is the only surviving record of why the collection stopped once
        # the live state has been cleared.
        "quarantine_cleared": quarantine if clear_quarantine else None,
    }
    assert_no_secret(json.dumps(note), "the supersede note")
    atomic_write_json(destination / "superseded.json", note, "supersede note")

    if state:
        # `stages_completed` is derived from the receipts at every start — `watch` recomputes it
        # from `assert_resume_is_safe` before dispatching — so this write keeps the file honest
        # between now and then rather than being the thing the supervisor trusts.
        state["stages_completed"] = after
        if clear_quarantine:
            state["quarantine"] = None
            state["state"] = STATE_WAITING
        write_state(state, state_path)
    return note


def is_retryable(message):
    lowered = str(message).lower()
    return any(marker in lowered for marker in RETRYABLE_MARKERS)


def poll_failure_diagnostic(error):
    """Enough to tell a DNS failure from a TLS one from a status code, and nothing private.

    Built from NAMED exception fields rather than `str(error)`: an `HTTPError` carries the full
    endpoint in its `url` attribute, and this endpoint's credential lives in its PATH. What is kept
    is the class, the HTTP status where there is one, and a `URLError`'s `reason` -- which is exactly
    where "Temporary failure in name resolution" and an SSL error text live, and which carries no
    endpoint. `assert_no_secret` still guards the result before it is written.

    The reason this exists at all: the run that died logged `type(error).__name__` and nothing else,
    so the one field that would have identified the cause was the one field not recorded.
    """
    name = type(error).__name__
    if isinstance(error, urllib.error.HTTPError):
        return f"{name} HTTP {error.code}"
    reason = getattr(error, "reason", None)
    if reason is not None:
        return f"{name}: {type(reason).__name__}: {reason}"
    return f"{name}: {error}"


def is_retryable_failure(error):
    """Type first for transport faults; message only for failures surfaced from the RPC layer.

    A DNS failure and a TLS failure are `URLError`s whose TEXT contains none of the transient
    markers, which is how one momentary name-resolution blip terminated a run built to survive days
    of waiting. Classifying transport faults by TYPE removes that whole class of mistake, rather than
    adding two more strings to a list that will always be missing the next one.

    `RETRYABLE_MARKERS` is kept for what it is actually good at: an RPC-level condition delivered
    inside a successful HTTP response, such as -32005 for a node that is behind. A plan or
    entitlement refusal is terminal there, because no retry changes an answer about who you are.
    """
    if isinstance(error, (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError)):
        # The type-based answer is FINAL for a transport fault: falling through to the message
        # matcher afterwards would let a 503's digits re-admit a status the policy had refused.
        return HTTP.is_retryable_error(error)
    lowered = str(error).lower()
    if any(marker in lowered for marker in NON_RETRYABLE_RPC_MARKERS):
        return False
    return is_retryable(error)


def record_quarantine(state, state_path, reason_code, diagnostic):
    """Persist the reason BEFORE raising, so the durable record cannot outlive the truth.

    A supervisor that exits on a quarantine while its state file still reads
    `waiting_for_maturity` tells an operator the run is healthy. That is what happened: the only
    thing that revealed the death was the liveness signal, and the reason existed nowhere but
    stderr, as a bare class name. `assert_manifest_unchanged` already wrote before raising; the
    polling path did not.

    The diagnostic is NOT scanned for secrets here. `write_state` reaches `atomic_write_json`, which
    already runs `assert_no_secret` over the whole payload, so a second call in this function could
    never fire — and a check nobody can provoke is worse than no check, because it reads as
    protection that was never tested. Two tests drive the real guard through this path: a diagnostic
    carrying an injected secret refuses the write and leaves no file, and a clean one writes.
    """
    if state is None:
        return None
    state["state"] = STATE_QUARANTINED
    state["quarantine"] = {"reason_code": reason_code, "diagnostic": diagnostic,
                           "at_wall_unix": int(time.time())}
    write_state(state, state_path)
    return state["quarantine"]


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


def poll_with_backoff(url, transport=None, retries=MAX_POLL_RETRIES, sleeper=time.sleep,
                      state=None, state_path=STATE_PATH):
    """Bounded retries with exponential backoff. Non-retryable failures quarantine immediately.

    Every terminal exit here persists its reason first. `state` is optional only so the function can
    be driven in isolation; the watcher always passes it, and a test asserts the write happens
    BEFORE the raise rather than in some cleanup that a crash could skip.

    Retry count, backoff base, cap and cadence are unchanged: only the classification moved, and the
    diagnostic that was missing is now recorded.
    """
    for attempt in range(retries):
        try:
            return poll_finalized_slot(url, transport=transport)
        except Quarantined as error:
            # Q04 already names its own reason. Persist it rather than leave the state file
            # claiming the run is still waiting.
            message = str(error)
            record_quarantine(state, state_path, message.split(":", 1)[0], message[:400])
            raise
        except Exception as error:                                   # noqa: BLE001 - classified
            diagnostic = poll_failure_diagnostic(error)
            if not is_retryable_failure(error):
                record_quarantine(state, state_path, Q06_NON_RETRYABLE_RPC, diagnostic)
                raise Quarantined(
                    f"{Q06_NON_RETRYABLE_RPC}: {diagnostic}. This is not a transport hiccup, and "
                    "retrying past it would be guessing about why it failed")
            if attempt == retries - 1:
                # Raised BEFORE sleeping again: the last backoff before giving up buys nothing and
                # the sleep is observable, which is what makes this bound testable.
                record_quarantine(
                    state, state_path, Q05_RETRIES_EXHAUSTED,
                    f"{retries} retryable failures in a row; last was {diagnostic}")
                raise Quarantined(
                    f"{Q05_RETRIES_EXHAUSTED}: {retries} retryable failures in a row. A retryable "
                    f"failure that keeps failing is not retryable in practice. Last: {diagnostic}")
            sleeper(min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt)))
    record_quarantine(state, state_path, Q05_RETRIES_EXHAUSTED, "no attempt was made")
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


def touch_stage_heartbeat(state, state_path, stdout_path=None, progressed=False, now=None):
    """Prove the SUPERVISOR is alive while it waits on a stage that may run for many hours.

    Two clocks, because they answer different questions. `stage_heartbeat_at` says the supervisor is
    still there. `stage_progress_at` says the STAGE is still producing, and only advances when the
    stage's output actually grew -- so a child that hangs while the supervisor keeps ticking shows a
    fresh heartbeat and a stalling progress age, which is the truth rather than a comfortable
    average of the two.
    """
    moment = int(time.time()) if now is None else now
    state["stage_heartbeat_at"] = moment
    if stdout_path is not None:
        path = pathlib.Path(stdout_path)
        size = path.stat().st_size if path.exists() else 0
        if size != state.get("stage_output_bytes"):
            state["stage_output_bytes"] = size
            progressed = True
    if progressed or state.get("stage_progress_at") is None:
        state["stage_progress_at"] = moment
    write_state(state, state_path)
    return state["stage_heartbeat_at"]


def run_stage(stage, command, state, runner=None, log_dir=LOG_DIR, receipt_dir=RECEIPT_DIR,
              state_path=STATE_PATH, heartbeat_seconds=STAGE_HEARTBEAT_SECONDS):
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
    state["stage_pid"] = None
    state["stage_output_bytes"] = 0
    touch_stage_heartbeat(state, state_path, progressed=True)

    started = int(time.time())
    if runner is None:
        with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=out, stderr=err, text=True)
            state["stage_pid"] = process.pid
            touch_stage_heartbeat(state, state_path, stdout_path=stdout_path)
            while True:
                try:
                    returncode = process.wait(timeout=heartbeat_seconds)
                    break
                except subprocess.TimeoutExpired:
                    # Waiting, not sleeping: the supervisor proves it is alive on every tick, and
                    # records the stage's output size so a HUNG child stays visible behind a
                    # perfectly healthy supervisor heartbeat.
                    touch_stage_heartbeat(state, state_path, stdout_path=stdout_path)
    else:
        returncode = runner(argv, stdout_path, stderr_path)
        touch_stage_heartbeat(state, state_path, stdout_path=stdout_path)
    finished = int(time.time())
    state["stage_pid"] = None

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


def status(state_path=STATE_PATH, receipt_dir=RECEIPT_DIR, lock_path=LOCK_PATH):
    """What an operator may see. Stage state and pass/fail; never a count."""
    state = read_state(state_path)
    signals = liveness(state, lock_path)
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
    assert_manifest_unchanged(state, state_path, manifest)
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

        tip = poll_with_backoff(url, transport=transport, sleeper=sleeper,
                                state=state, state_path=state_path)
        state["polls"] += 1
        state["last_tip_slot"] = tip
        state["last_poll_at"] = int(time.time())
        verdict = B11A.maturity(tip)
        if not verdict["mature"]:
            state["state"] = STATE_WAITING
            write_state(state, state_path)
            sleeper(poll_seconds)
            continue

        # Re-checked here, at the transition from waiting to running: this is the last instant
        # before any stage executes, and everything between here and the start attestation was
        # dead time in which the scripts could have moved.
        assert_manifest_unchanged(state, state_path)
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
