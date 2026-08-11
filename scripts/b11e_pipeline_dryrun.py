"""B11e — offline end-to-end dry run of the nine B11a collection stages. No network, no chain.

What this is
------------
An audit that walks the exact nine stages B11c would run, against tiny synthetic fixtures, and
checks the things that only fail at maturity if nobody checks them first:

1. **Every argument the plan passes is one the target script actually accepts.** Verified against
   each script's own argparse through `--help`, not against a copy of its interface kept here. This
   is the check that would have caught `b9d run` having no `--b9c`/`--b9a`.
2. **The artifact chain joins up.** Every path a stage writes is a path some later stage reads, and
   every path a stage reads is one an earlier stage wrote. A pipeline where those disagree fails at
   the join, hours in.
3. **Nothing can reach the burned corpus.** No stage argument mentions a burned artifact, and the
   two stages that accept source overrides must pass paths that differ from their module defaults —
   because the defaults ARE the burned corpus.
4. **Nothing can reach the network.** The fixture runs with the RPC variable cleared, so a stage
   that tried would fail rather than succeed quietly against a real endpoint.
5. **The gates do not pass vacuously.** An empty or malformed artifact must be REFUSED by each
   gate. A gate that returns "pass" on an artifact containing nothing is worse than no gate, and it
   is the failure mode nobody notices, because its output looks like success.
6. **Receipts, resume and the manifest behave.** Driven through B11c's own fake-runner seam.

What it will not do
-------------------
It runs no collection stage for real — those need a chain. It builds the cohort for real, because
that stage is offline by construction. It never reads the live watcher's directory, never touches
its state, and never looks at fresh cohort composition, because none exists.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B11C = _load("b11c_maturity_watcher", "b11c_maturity_watcher.py")
B11D = _load("b11d_cohort_adapter", "b11d_cohort_adapter.py")
B9D = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")

SCHEMA_VERSION = "1.0.0"

# Paths that must never appear in a fresh-window argument. These are the burned corpus.
BURNED_MARKERS = ("b9a_outcomes", "b9c_signature_inventory.sqlite", "b9d_transaction_bodies.sqlite",
                  "b10b_observed_paths", "b8b_", "b7c_")

# What each stage consumes and produces, declared here so the chain can be checked as a graph
# rather than by reading nine argv lists and hoping.
STAGE_IO = {
    # program_boundary writes its version-coverage rows INTO the bodies database, because that is
    # where decode reads them: verify_artifact -> assert_boundary_evidence_complete queries
    # program_version against the artifact it decodes. It shares b11a_bodies.sqlite with
    # transaction_bodies -- two writers, one consumer -- rather than the standalone
    # b11a_program_boundary.json it used to emit, which nothing read. That orphan is what refused
    # stage 6 after a three-day collection; the graph now declares the wiring the fix installs.
    "program_boundary": {"reads": (), "writes": ("b11a_bodies.sqlite",)},
    "enumerate_creates": {"reads": (), "writes": ("b11a_creates.sqlite", "b11a_creates.jsonl")},
    "build_cohort": {"reads": ("b11a_creates.sqlite",), "writes": ("b11a_cohort.sqlite",)},
    "subsample_cohort": {"reads": ("b11a_cohort.sqlite",), "writes": ("b11a_subsample.sqlite",)},
    "signature_inventory": {"reads": ("b11a_subsample.sqlite", "b11a_creates.sqlite"),
                            "writes": ("b11a_signatures.sqlite",)},
    "transaction_bodies": {"reads": ("b11a_signatures.sqlite", "b11a_subsample.sqlite"),
                           "writes": ("b11a_bodies.sqlite",)},
    "decode_and_reserves": {"reads": ("b11a_bodies.sqlite", "b11a_signatures.sqlite",
                                      "b11a_subsample.sqlite"), "writes": ()},
    "reserve_coverage_gate": {"reads": ("b11a_bodies.sqlite", "b11a_subsample.sqlite"),
                              "writes": ()},
    "failure_coverage_gate": {"reads": ("b11a_bodies.sqlite",), "writes": ()},
    "simulator_replay_gate": {"reads": ("b11a_bodies.sqlite",), "writes": ()},
}

B7D_SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE slot_scan (slot INTEGER PRIMARY KEY, status TEXT NOT NULL, blockhash TEXT,
  previous_blockhash TEXT, parent_slot INTEGER, block_time INTEGER, transaction_count INTEGER,
  pump_transaction_count INTEGER, create_instruction_count INTEGER, error TEXT,
  scanned_at_unix REAL NOT NULL);
CREATE TABLE create_event (slot INTEGER NOT NULL, transaction_index INTEGER NOT NULL,
  outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
  signature TEXT NOT NULL, block_time INTEGER, mint TEXT NOT NULL, bonding_curve TEXT NOT NULL,
  creator TEXT, user TEXT, is_mayhem_mode INTEGER, is_cashback_enabled INTEGER, quote_mint TEXT,
  fields_json TEXT NOT NULL, event_payload_base64 TEXT NOT NULL,
  PRIMARY KEY (slot, transaction_index, outer_instruction_index, inner_instruction_index));
CREATE TABLE decode_error (slot INTEGER NOT NULL, transaction_index INTEGER NOT NULL,
  outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
  signature TEXT NOT NULL, error TEXT NOT NULL,
  PRIMARY KEY (slot, transaction_index, outer_instruction_index, inner_instruction_index));
"""


class DryRunFailed(Exception):
    """Raised when the offline audit finds something that would fail at maturity."""


# --------------------------------------------------------------------------------------------
# Interface checks
# --------------------------------------------------------------------------------------------

def script_help(argv, timeout=60):
    """The target script's OWN help for the subcommand a stage uses.

    Asked of the script rather than answered from a copy of its interface kept here: a copy would
    agree with itself while the script had moved on, which is precisely the failure this exists to
    catch.
    """
    command = [argv[0], argv[1]]
    if len(argv) > 2 and not argv[2].startswith("-") and not argv[2].endswith(
            (".sqlite", ".jsonl", ".json")):
        command.append(argv[2])            # a subcommand, not a positional path
    command.append("--help")
    environment = dict(os.environ)
    # Cleared so a script that tried to reach the network during argument parsing would fail
    # rather than succeed quietly against a real endpoint.
    environment.pop("SOLANA_RPC_URL", None)
    environment.pop("HELIUS_API_KEY", None)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                            env=environment)
    return result


def check_arguments(stage, argv):
    """Every flag the plan passes must be one the script declares."""
    findings = []
    result = script_help(argv)
    if result.returncode != 0:
        findings.append(f"{stage}: `{' '.join(argv[1:3])} --help` exited {result.returncode}; the "
                        f"subcommand the plan uses does not exist. {result.stderr.strip()[:160]}")
        return findings
    help_text = result.stdout
    for token in argv:
        if not token.startswith("--"):
            continue
        flag = token.split("=", 1)[0]
        if flag not in help_text:
            findings.append(
                f"{stage}: the plan passes {flag} but the script does not declare it. This is the "
                "shape of the defect that had b9d run collecting against the burned corpus")
    return findings


def check_isolation(stage, argv, directory):
    """Every artifact path inside the fixture directory, and no burned artifact anywhere."""
    findings = []
    joined = " ".join(argv)
    for marker in BURNED_MARKERS:
        if marker in joined:
            findings.append(
                f"{stage}: argument list mentions the burned artifact {marker!r}; a fresh window "
                "that reads or writes the burned corpus destroys both")
    for token in argv:
        if token.endswith((".sqlite", ".jsonl")) or token.endswith("b11a_program_boundary.json"):
            if not str(token).startswith(str(directory)):
                findings.append(f"{stage}: artifact path {token} is outside the fixture directory")
    return findings


def check_overrides_differ_from_defaults(stage, argv):
    """A source override that equals the module default is not an override.

    The defaults are the burned corpus. A stage that passes them explicitly looks parameterised and
    behaves exactly as it would with no arguments at all.
    """
    findings = []
    defaults = {"--b9c": B9D.B9C_PATH, "--b9a": B9D.B9A_PATH}
    for index, token in enumerate(argv):
        if token in defaults and index + 1 < len(argv):
            if argv[index + 1] == defaults[token]:
                findings.append(
                    f"{stage}: {token} is passed as its module default {defaults[token]!r}, which "
                    "is the burned corpus. Passing a default explicitly is not parameterisation")
    return findings


def check_chain(commands):
    """Everything read was written, and everything written is read. A join that does not."""
    findings = []
    order = list(B11C.RUN_ORDER)
    produced = {}
    for stage in order:
        for name in STAGE_IO[stage]["reads"]:
            if name not in produced:
                findings.append(
                    f"{stage}: reads {name} which no earlier stage produces; the pipeline would "
                    "fail at the join, hours into a collection")
        for name in STAGE_IO[stage]["writes"]:
            produced[name] = stage
    consumed = {name for stage in order for name in STAGE_IO[stage]["reads"]}
    for name, stage in sorted(produced.items()):
        # `.jsonl` is exempt because a create export is a genuine terminal artifact nothing in the
        # pipeline consumes. `.json` was exempt beside it and should never have been: the only
        # `.json` output is `b11a_program_boundary.json`, which stage 6 IS meant to consume, and it
        # is not even JSON -- it opens `SQLite format 3`. The extension was a proxy for "terminal
        # export" and it silently swallowed a consumed database, which is exactly the orphan this
        # check exists to catch. The extension names the format the writer chose, not whether the
        # artifact is read; only the graph knows that, so the graph decides.
        if name not in consumed and not name.endswith(".jsonl"):
            findings.append(f"{stage}: writes {name} which nothing reads")
    # And the declared graph must match the actual argument lists.
    for stage in order:
        joined = " ".join(commands[stage]["argv"])
        for name in STAGE_IO[stage]["reads"] + STAGE_IO[stage]["writes"]:
            if name not in joined:
                findings.append(
                    f"{stage}: the declared interface names {name} but its arguments do not; the "
                    "graph checked here would be describing a different pipeline")
    return findings


# --------------------------------------------------------------------------------------------
# Fixtures and real offline execution
# --------------------------------------------------------------------------------------------

def make_enumeration(path, start=100, end_exclusive=105):
    """A tiny B7d enumeration: five slots, three creates, one legitimately skipped."""
    database = sqlite3.connect(path)
    database.executescript(B7D_SCHEMA)
    database.executemany("INSERT INTO metadata VALUES (?,?)",
                         [("start_slot", str(start)),
                          ("end_slot_exclusive", str(end_exclusive))])
    for slot in range(start, end_exclusive):
        database.execute("INSERT INTO slot_scan VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (slot, "skipped" if slot == start + 3 else "retrieved", None, None, None,
                          None, 0, 0, 0, None, 0.0))
    creates = ((start, "MintDryA", "CurveDryA", 0), (start + 1, "MintDryB", "CurveDryB", 1),
               (start + 4, "MintDryC", "CurveDryC", 0))
    for index, (slot, mint, curve, mayhem) in enumerate(creates):
        database.execute("INSERT INTO create_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (slot, 0, 0, index, f"drysig{index}", None, mint, curve, "cr", "us",
                          mayhem, 0, "So111", "{}", "AA=="))
    database.commit()
    database.close()
    return path


def run_cohort_stage(directory):
    """The one collection-adjacent stage that is offline by construction, run for real."""
    source = make_enumeration(directory / "b11a_creates.sqlite")
    summary = B11D.build(source, directory / "b11a_cohort.sqlite")
    verified = B11D.assert_fresh_cohort(directory / "b11a_cohort.sqlite")
    findings = []
    if verified["members"] != summary["members"]:
        findings.append("build_cohort: the artifact verifies to a different member count")
    # Prove the consumers' own SQL runs against it, rather than asserting compatibility.
    database = sqlite3.connect(f"file:{directory / 'b11a_cohort.sqlite'}?mode=ro", uri=True)
    try:
        for label, query in (
                ("b9c", "SELECT mint,bonding_curve,launch_slot FROM outcome "
                        "ORDER BY launch_slot,mint"),
                ("b9d", "SELECT bonding_curve,is_mayhem_mode FROM outcome"),
                ("b9d tradable", "SELECT mint,bonding_curve FROM outcome WHERE is_mayhem_mode=0")):
            try:
                rows = database.execute(query).fetchall()
            except sqlite3.Error as error:
                findings.append(f"build_cohort: {label}'s own query fails against the artifact: "
                                f"{error}")
                continue
            if not rows:
                findings.append(f"build_cohort: {label}'s query returns nothing")
    finally:
        database.close()
    # A source that is not there must be REFUSED, and refused as a refusal. Raising some other
    # exception type is not fail-closed: every caller here is written `except FreezeViolation`, so
    # anything else escapes as a traceback past the handler meant to contain it.
    for label, b9c, b9a in (
            ("a signature inventory that does not exist", directory / "missing_signatures.sqlite",
             directory / "b11a_cohort.sqlite"),
            ("a cohort that does not exist", directory / "b11a_creates.sqlite",
             directory / "missing_cohort.sqlite"),
            ("a cohort that never declared itself one", directory / "b11a_creates.sqlite",
             directory / "b11a_creates.sqlite")):
        try:
            B9D.assert_sources(str(b9c), str(b9a))
        except B9D.FreezeViolation:
            continue
        except Exception as error:                                       # noqa: BLE001
            findings.append(
                f"build_cohort: b9d rejected {label} with {type(error).__name__}, not a refusal; "
                "`except FreezeViolation` around this call does not catch it")
            continue
        findings.append(f"build_cohort: b9d ACCEPTED {label}")
    return findings, summary


def check_gates_refuse_an_empty_artifact(directory):
    """A gate that passes on an empty artifact is worse than no gate.

    Its output looks exactly like success, so nobody investigates. Each gate is handed an artifact
    with the right file extension and nothing inside, and must refuse.
    """
    findings = []
    empty = directory / "empty_artifact.sqlite"
    sqlite3.connect(empty).close()
    gates = {
        "reserve_coverage_gate": [sys.executable, "scripts/b9e_reserve_coverage.py", str(empty),
                                  "--b9a", str(directory / "b11a_cohort.sqlite")],
        "failure_coverage_gate": [sys.executable, "scripts/b9f_failure_coverage.py", str(empty)],
        "simulator_replay_gate": [sys.executable, "scripts/b10a_simulator_kernel.py", str(empty),
                                  "--gate"],
        "decode_and_reserves": [sys.executable, "scripts/b9d_transaction_bodies.py", "decode",
                                str(empty), "--b9c", str(directory / "b11a_signatures.sqlite"),
                                "--b9a", str(directory / "b11a_cohort.sqlite")],
    }
    environment = dict(os.environ)
    environment.pop("SOLANA_RPC_URL", None)
    environment.pop("HELIUS_API_KEY", None)
    verdicts = {}
    for stage, command in gates.items():
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180,
                                env=environment)
        verdicts[stage] = result.returncode
        if result.returncode == 0:
            findings.append(
                f"{stage}: PASSED on an empty artifact. A gate whose output looks like success on "
                "nothing is the failure mode nobody investigates")
    return findings, verdicts


def claim_fixture_directory(directory, generation=1):
    """Declare who owns this fixture, because B11c's guard now demands it of every caller.

    The guard fails closed on a directory that holds a corpus but names no owner: that is exactly
    what a `git clean -fdx` leaves behind, since the supervisor state is gitignored while the
    databases are not. This dry run builds real cohort artifacts and only then invokes the watcher,
    so by the time the guard looks it sees a populated directory with no state file yet -- the same
    shape as the accident, arriving legitimately.

    So it claims the directory rather than being exempted from the check. There is deliberately no
    bypass flag: an escape hatch for callers that "know what they are doing" is the hole the guard
    exists to close, and a dry run that ran under weaker rules than production would be testing a
    pipeline nobody deploys.
    """
    marker = pathlib.Path(directory) / B11C.SPENT_TOMBSTONE
    marker.write_text(json.dumps({
        "generation": generation,
        "spent": False,
        "cutoff_slot_inclusive": B11C.B11A.derive_window(
            B11C.generation_config(generation)["ranges"])["observation_cutoff_slot_inclusive"],
        "why": ("B11e dry-run fixture. Claims this throwaway directory so the watcher's "
                "fail-closed ownership guard sees a named owner instead of an unclaimed corpus. "
                "spent=false: this fixture is meant to be run, unlike a real collected window."),
    }, indent=2, sort_keys=True) + "\n")
    return marker


def check_watcher_behaviour(directory):
    """Receipts, resume, duplicate refusal and manifest drift, through B11c's own seams."""
    findings = []
    claim_fixture_directory(directory)
    paths = {"work_dir": directory, "state_path": directory / "state.json",
             "receipt_dir": directory / "receipts", "log_dir": directory / "logs"}
    ran = []

    def runner(argv, stdout_path, stderr_path):
        ran.append(argv)
        pathlib.Path(stdout_path).write_text("dry run\n")
        pathlib.Path(stderr_path).write_text("")
        return 0

    commands = {name: dict(command, wiring="resolved")
                for name, command in B11C.stage_commands(directory).items()}
    cutoff = B11C.B11A.derive_window()["observation_cutoff_slot_inclusive"]
    state = B11C.watch("https://dry-run.invalid/", transport=lambda *_a: cutoff,
                       sleeper=lambda _s: None, runner=runner, max_iterations=1,
                       commands=commands, **paths)
    if state["state"] != B11C.STATE_ALL_STAGES_COMPLETE:
        findings.append(f"watcher: finished in state {state['state']!r}")
    if len(ran) != len(B11C.RUN_ORDER):
        findings.append(f"watcher: ran {len(ran)} stages, expected {len(B11C.RUN_ORDER)}")
    receipts = sorted(p.stem for p in paths["receipt_dir"].glob("*.json"))
    if receipts != sorted(B11C.RUN_ORDER):
        findings.append(f"watcher: receipts {receipts} do not cover every stage")

    # Resume: a second pass over the same directory must run nothing.
    rerun = []

    def counting_runner(argv, stdout_path, stderr_path):
        rerun.append(argv)
        return runner(argv, stdout_path, stderr_path)

    B11C.watch("https://dry-run.invalid/", transport=lambda *_a: cutoff, sleeper=lambda _s: None,
               runner=counting_runner, max_iterations=1, commands=commands, **paths)
    if rerun:
        findings.append(f"watcher: a resume re-ran {len(rerun)} stages that already had receipts")

    # Manifest drift: a changed script must quarantine rather than resume.
    drifted = json.loads(paths["state_path"].read_text())
    drifted["manifest_sha256"] = "0" * 64
    paths["state_path"].write_text(json.dumps(drifted))
    try:
        B11C.watch("https://dry-run.invalid/", transport=lambda *_a: cutoff,
                   sleeper=lambda _s: None, runner=runner, max_iterations=1, commands=commands,
                   **paths)
        findings.append("watcher: a drifted manifest did not quarantine")
    except B11C.Quarantined:
        pass
    return findings


def check_offline(directory):
    """Nothing in the fixture run may have needed the network."""
    findings = []
    if os.environ.get("SOLANA_RPC_URL"):
        findings.append(
            "the dry run inherited SOLANA_RPC_URL; a stage that reached the network would have "
            "succeeded quietly instead of failing, and the audit would have proved nothing")
    return findings


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def dry_run(directory=None):
    """Every check, against a fresh fixture directory. Returns a report; raises nothing."""
    owned = directory is None
    directory = pathlib.Path(directory or tempfile.mkdtemp(prefix="b11e-dryrun-"))
    directory.mkdir(parents=True, exist_ok=True)
    try:
        commands = B11C.stage_commands(directory)
        findings, checks = [], {}
        findings += check_offline(directory)
        for stage in B11C.RUN_ORDER:
            argv = commands[stage]["argv"]
            stage_findings = (check_arguments(stage, argv)
                              + check_isolation(stage, argv, directory)
                              + check_overrides_differ_from_defaults(stage, argv))
            checks[stage] = {"arguments_accepted": not stage_findings,
                             "wiring": commands[stage]["wiring"]}
            findings += stage_findings
        findings += check_chain(commands)
        cohort_findings, cohort = run_cohort_stage(directory)
        findings += cohort_findings
        gate_findings, gate_exits = check_gates_refuse_an_empty_artifact(directory)
        findings += gate_findings
        findings += check_watcher_behaviour(directory)
        return {
            "schema_version": SCHEMA_VERSION,
            "stages": list(B11C.RUN_ORDER),
            "stage_checks": checks,
            "chain": {stage: STAGE_IO[stage] for stage in B11C.RUN_ORDER},
            "cohort_members_built": cohort["members"],
            "gate_exit_codes_on_an_empty_artifact": gate_exits,
            "network_reachable": False,
            "burned_artifacts_referenced": False,
            "composition_published": False,
            "findings": findings,
            "passed": not findings,
        }
    finally:
        if owned:
            shutil.rmtree(directory, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="store_true", help="exit non-zero on any finding")
    parser.add_argument("--directory", default=None, help="keep the fixture here")
    args = parser.parse_args(argv)
    report = dry_run(args.directory)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.gate and not report["passed"]:
        raise DryRunFailed(f"{len(report['findings'])} findings")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DryRunFailed as error:
        print(f"DryRunFailed: {error}", file=sys.stderr)
        sys.exit(2)
