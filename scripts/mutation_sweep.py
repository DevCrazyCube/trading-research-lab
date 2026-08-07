"""Reproducible mutation sweeps.

WHY THIS EXISTS. 131 of this repository's 270 commits cite mutation evidence in their message —
"24/24 killed, 0 survivors" and the like — and until now every sweep that produced those numbers
lived in a scratch directory and was deleted at session end. A reader could re-run the test suite
and could not re-run the thing that establishes the suite is worth anything. Mutation numbers were
trust-me numbers, which is the same species as the failure `B17C_SHADOW_READINESS_GAP_MAP.md`
exists for: a claim that cannot be checked from the artefact.

A SWEEP IS AN ARTEFACT THAT DESCRIBES THE TESTS, SO BY THIS PROJECT'S OWN STANDING LESSON IT MAY
NOT BE TRUSTED TO DESCRIBE ITSELF. The obvious implementation fails in two ways that both look
like success:

- a sweep that declares twenty mutants and silently applies sixteen reports 16/16 killed;
- a sweep whose patterns stop matching after a refactor applies nothing and reports 0/0, a clean
  sweep with no content.

So a pattern that does not match is a REFUSAL here, never a skip, and a sweep declaring no mutants
is refused outright. Both guards exist because their absence is invisible.

A KILLED MUTANT MEANS NOTHING WITHOUT A GREEN BASELINE. If a test is already failing, every mutant
"dies" and the sweep reports a perfect score carrying no information — the check-that-cannot-fire
rule one level up. The unmutated suite is run first and the sweep refuses unless it passes.

NOTHING IS EVER MUTATED IN THE WORKING TREE. A live watcher has run for days in this repository and
holds its code in memory, and four files are manifest-pinned; a sweep that edits `scripts/` in place
is a footgun the first time someone interrupts one, because restore-in-finally does not survive
SIGKILL. Every mutant is applied to a STAGED COPY of the git-tracked tree whose root is a scratch
directory, so the working tree cannot be reached rather than merely being carefully avoided — the
same upgrade `b18c` made over being careful. The working tree is additionally re-hashed and asserted
byte-identical on exit, so the structural claim is checked and not just asserted.

SURVIVORS ARE DECLARED IN DATA. A mutant that survives because its property is covered elsewhere is
a judgement, and judgements belong where they can be re-checked. A sweep refuses if an undeclared
mutant survives, and equally if a DECLARED survivor is suddenly killed — the second because it means
the coverage moved and somebody should find out from a failure rather than from a surprise.

Sweeps are NOT part of the default test suite. `b18c`'s costs roughly nine minutes against its own
22-second suite; a repository-wide sweep dwarfs the full run, and a suite people stop running is a
worse outcome than the gap this fixes. Run one deliberately:

    python scripts/mutation_sweep.py b19

This module runs the test suite in a subprocess and opens no socket, signs nothing and spends
nothing.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SWEEP_DIR = ROOT / "research" / "mutation"


# Exactly the fields a declaration may carry, on b12a's precedent: it refuses an unknown risk-config
# field because "a misspelled limit is an absent limit wearing a plausible name". The same is true
# here and worse — a mutant carrying `find` instead of `old` would be silently inert, and an inert
# mutant is one this sweep counts as applied while it changes nothing.
DECLARATION_FIELDS = ("sweep_id", "description", "target", "tests", "mutants",
                      "expected_survivors", "expected_survivors_note")

# The ONLY tracked paths the tree check ignores, named rather than skipped silently.
#
# `agent_discussion.md` is the append-only human audit log the dashboard writes on every handoff.
# No test reads it and nothing in it can change a test outcome, but a sweep takes minutes and the
# collaboration protocol's whole job is to run concurrently with work — so a strict check makes
# "send a colleague a message" and "run a sweep" mutually exclusive, and a guard that forbids
# colleagues from talking is a guard somebody disables. That is a worse outcome than this narrow,
# stated exception. Bounded on purpose: a test asserts a change to ANYTHING ELSE still refuses.
TREE_MANIFEST_EXCLUSIONS = ("agent_discussion.md",)

MUTANT_FIELDS = ("name", "old", "new", "note")
SURVIVOR_FIELDS = ("name", "why")


class SweepRefused(RuntimeError):
    """The sweep cannot produce a number it is willing to stand behind, so it produces none.

    Deliberately not a warning and not a zero. A sweep that reported "0 survivors" after failing to
    apply its mutants would be indistinguishable from a clean one, which is the failure this whole
    module is built against.
    """


def load_sweep(name, sweep_dir=SWEEP_DIR):
    path = pathlib.Path(sweep_dir) / f"{name}.sweep.json"
    if not path.is_file():
        raise SweepRefused(
            f"no sweep declaration at {path}; an undeclared sweep is not an empty one")
    declaration = json.loads(path.read_bytes())
    assert_declaration(declaration, name)
    return declaration


def assert_declaration(declaration, name):
    """A declaration must say enough that its result can be disbelieved."""
    for field in ("sweep_id", "target", "tests", "mutants", "expected_survivors"):
        if field not in declaration:
            raise SweepRefused(f"{name}: the declaration does not state {field!r}")

    if declaration["sweep_id"] != name:
        raise SweepRefused(
            f"the declaration calls itself {declaration['sweep_id']!r} but was loaded as {name!r}")

    unknown = [field for field in declaration if field not in DECLARATION_FIELDS]
    if unknown:
        raise SweepRefused(
            f"{name}: the declaration carries unknown field(s) {sorted(unknown)}. A misspelled "
            "field is an absent field wearing a plausible name, and an author who believes it is "
            "doing something is worse off than one who left it out")

    mutants = declaration["mutants"]
    if not isinstance(mutants, list) or not mutants:
        raise SweepRefused(
            f"{name} declares no mutants. A sweep with nothing to apply reports a perfect score "
            "and establishes nothing; that is the check-that-cannot-fire failure as a whole file")

    seen = set()
    for mutant in mutants:
        for field in ("name", "old", "new"):
            if field not in mutant:
                raise SweepRefused(f"{name}: a mutant does not state {field!r}: {mutant!r}")
        unknown_mutant = [field for field in mutant if field not in MUTANT_FIELDS]
        if unknown_mutant:
            raise SweepRefused(
                f"{name}: mutant {mutant.get('name')!r} carries unknown field(s) "
                f"{sorted(unknown_mutant)}. A mutant whose pattern is spelled into a field this "
                "sweep never reads is inert, and an inert mutant is counted as applied")
        if mutant["old"] == mutant["new"]:
            raise SweepRefused(
                f"{name}: mutant {mutant['name']!r} replaces its pattern with itself, so it "
                "cannot change behaviour and would always be recorded as a survivor")
        if mutant["name"] in seen:
            raise SweepRefused(f"{name}: two mutants are both called {mutant['name']!r}")
        seen.add(mutant["name"])

    for expected in declaration["expected_survivors"]:
        unknown_survivor = [field for field in expected if field not in SURVIVOR_FIELDS]
        if unknown_survivor:
            raise SweepRefused(
                f"{name}: declared survivor {expected.get('name')!r} carries unknown field(s) "
                f"{sorted(unknown_survivor)}")
        for field in ("name", "why"):
            if field not in expected:
                raise SweepRefused(
                    f"{name}: a declared survivor does not state {field!r}: {expected!r}. A "
                    "survivor without a justification is an unexplained failure wearing a label")
        if expected["name"] not in seen:
            raise SweepRefused(
                f"{name}: {expected['name']!r} is declared as an expected survivor but is not one "
                "of the mutants; a stale declaration would silence a real survivor by that name")
    return declaration


def tracked_files(root=ROOT):
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [name for name in result.stdout.decode().split("\0") if name]


def stage_tree(destination, root=ROOT):
    """Copy the git-tracked tree into a scratch directory.

    Tracked files only: the ignored artifacts in `research/` run to gigabytes and none of them is
    input to a guard. What is copied is exactly what a reader could check out, which is the point —
    the number this produces must be reproducible from the repository and not from local state.
    """
    destination = pathlib.Path(destination)
    for name in tracked_files(root):
        source = pathlib.Path(root) / name
        if not source.is_file():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def first_failing_test(output):
    """The FIRST test that failed under a mutant — which is NOT necessarily the guard responsible.

    WHAT THIS FIELD CANNOT DO, stated here because it was originally built to do it. The suggestion
    (claude seat, handoff 204) was to answer the standing lesson "a test killed by a different
    guard than the one it names is not testing that guard". It cannot. The sweep runs pytest with
    `-x`, so the run stops at the first failure, and `unittest` orders tests alphabetically within
    a class — so this records whichever killer sorts first, not the one that matters.

    Verified rather than reasoned about, by both seats independently: b18a's mutant "the tip
    defaults to zero instead of null" is recorded as killed by
    `test_a_non_nullable_field_may_not_be_null`, and applying the mutant shows that test AND
    `test_no_unmeasured_field_was_defaulted_to_zero_or_false` each kill it on their own. An audit
    built on this field returned 21 suspects that were nearly all artifacts of the ordering.

    So the field is named for what it measures. Answering the section-7 question needs the FULL
    failure set, which `-x` discards by design; getting it means running every mutant against its
    whole test file — 26 x 73 on b18c — and that is worth an opt-in flag, not a default.

    What it IS good for: a killer that is obviously unrelated to its mutant is still worth a look.
    That is how the b18b mutant "a 403 becomes retryable" was found to be MISNAMED rather than
    miskilled — its recorded killer was correct and the mutant's name was not.

    BOTH pytest failure prefixes are parsed. `FAILED` is the ordinary one; `SUBFAILED` is what a
    failing `subTest` produces, and this project uses subtests heavily — 3,242 of them. Matching
    only `FAILED` returned None for every mutant killed by a subtest, which is the same defect in
    miniature as the thing the field exists to expose: a killer that is not recorded cannot be
    checked against the guard it is supposed to name.
    """
    for line in output.splitlines():
        for prefix in ("FAILED ", "SUBFAILED"):
            if line.startswith(prefix):
                # SUBFAILED carries its parameters in brackets before the test id.
                remainder = line[len(prefix):].split(" - ")[0].strip()
                if remainder.startswith("("):
                    remainder = remainder.split(")", 1)[-1].strip()
                return remainder or None
    return None


def _run_tests(staged_root, tests, timeout):
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *tests, "-x", "-q"],
            cwd=staged_root, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout[-2000:]
    except subprocess.TimeoutExpired:
        # A mutant that hangs is killed: the suite did not pass. Reported distinctly so a sweep
        # whose runtime quietly exploded is visible rather than merely slow.
        return "timeout", ""


def assert_within(path, root, name):
    """Refuse a target that escapes the staging root.

    Extracted rather than left inline. Inline, its condition is always false — staging builds the
    path itself — so it would be a check that cannot fire, which reads as protection while testing
    nothing and would survive any mutation. As a function a test can hand it a crafted path, which
    is the standing remedy in the gap map's section 7.
    """
    if not pathlib.Path(path).resolve().is_relative_to(pathlib.Path(root).resolve()):
        raise SweepRefused(
            f"{name}: the staged target {path} escapes the staging root {root}; refusing rather "
            "than mutating anything that might be the working tree")
    return path


def assert_tree_unchanged(before, after, name):
    """Refuse if the working tree moved during a sweep, NAMING what moved.

    Extracted for the same reason as `assert_within`: nothing in a correct run can make this fire,
    so inline it would be untestable and unmutatable. It exists for the run that is not correct.

    It takes per-path manifests rather than one digest because the first version took digests and
    could therefore only say "something did". The claude seat hit that refusal for real and had to
    hash every tracked file by hand to discover the cause was two files I had edited during their
    sweep. A guard that detects a problem it cannot describe costs its reader the diagnosis.
    """
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(path for path in set(before) & set(after) if before[path] != after[path])
    if added or removed or modified:
        raise SweepRefused(
            f"{name}: the working tree changed during the sweep. Nothing here may write outside "
            f"the staging root and something did. modified={modified} added={added} "
            f"removed={removed}")
    return after


def _tree_manifest(root, names):
    """Per-path digest of the tracked tree, so a refusal can name what moved."""
    manifest = {}
    for name in sorted(names):
        if name in TREE_MANIFEST_EXCLUSIONS:
            continue
        path = pathlib.Path(root) / name
        manifest[name] = (hashlib.sha256(path.read_bytes()).hexdigest()
                          if path.is_file() else "<absent>")
    return manifest


def _manifest_digest(manifest):
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def acquire_lock(sweep_dir, name):
    """Refuse to start while another sweep is running, rather than colliding nine minutes later.

    Two concurrent sweeps always collided before this existed: each writes its own result file
    into the working tree at the end, which trips the other's tree check — and the message it
    produced was about escaping the staging root, which is alarming and wrong. An accurate refusal
    up front is worth more than an alarming one after the work is wasted.

    A stale lock REFUSES rather than being silently stolen, and says how to clear it. Stealing a
    lock whose owner might still be running is how the collision comes back wearing a hat.

    The lock is untracked, so it is invisible to the tree manifest by construction.
    """
    lock = pathlib.Path(sweep_dir) / ".sweep.lock"
    if lock.exists():
        raise SweepRefused(
            f"{name}: another sweep holds the lock — {lock.read_text().strip()}. Sweeps write "
            f"their results into the working tree, so two at once corrupt each other's tree "
            f"check. If that process is gone, delete {lock}")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"sweep={name} pid={os.getpid()}")
    return lock


def run_sweep(name, root=ROOT, sweep_dir=SWEEP_DIR, timeout=600, staging_root=None):
    """Apply every declared mutant against a staged copy and return the result."""
    root = pathlib.Path(root)
    declaration = load_sweep(name, sweep_dir)
    target_name = declaration["target"]
    tests = declaration["tests"]

    tracked = tracked_files(root)
    if target_name not in tracked:
        raise SweepRefused(
            f"{name}: target {target_name} is not tracked by git, so a reader could not reproduce "
            "this sweep from the repository")
    before = _tree_manifest(root, tracked)

    lock = acquire_lock(sweep_dir, name)
    scratch = pathlib.Path(staging_root or tempfile.mkdtemp(prefix="mutation-sweep-"))
    staged_root = scratch / "tree"
    staged_root.mkdir(parents=True, exist_ok=True)
    try:
        stage_tree(staged_root, root)
        # Structural, not a promise: everything below writes only under `staged_root`.
        target = assert_within(staged_root / target_name, staged_root, name)
        original = target.read_text()

        baseline_code, baseline_output = _run_tests(staged_root, tests, timeout)
        if baseline_code != 0:
            raise SweepRefused(
                f"{name}: the unmutated suite does not pass in the staged tree (exit "
                f"{baseline_code}). Every mutant would 'die' against an already-failing suite and "
                f"the sweep would report a perfect score carrying no information.\n{baseline_output}")

        killed, survivors, records = [], [], []
        for mutant in declaration["mutants"]:
            if mutant["old"] not in original:
                raise SweepRefused(
                    f"{name}: mutant {mutant['name']!r} does not match the target. It was never "
                    "applied, and an unapplied mutant silently inflates the score — a sweep that "
                    "skips is a sweep that lies")
            target.write_text(original.replace(mutant["old"], mutant["new"], 1))
            try:
                code, output = _run_tests(staged_root, tests, timeout)
            finally:
                target.write_text(original)
            if code == 0:
                survivors.append(mutant["name"])
            else:
                killed.append(mutant["name"])
            records.append({
                "name": mutant["name"],
                "outcome": "survived" if code == 0 else "killed",
                # Named for what it measures: the FIRST failure under `-x`, not the responsible
                # guard. See first_failing_test — several tests often kill one mutant and this
                # records whichever sorts first. It was called `killed_by` until that was
                # measured, and the old name invited exactly the inference it cannot support.
                #
                # A killed mutant whose killer could not be parsed reports a reason code rather
                # than null. Null here would mean "no killer", which is what a SURVIVOR reports,
                # and collapsing "nothing killed it" into "we could not tell what killed it" is
                # the zero-standing-in-for-an-unknown failure with a different name.
                "first_failing_test": None if code == 0 else (
                    "timeout" if code == "timeout"
                    else first_failing_test(output) or "U_KILLER_NOT_PARSED"),
            })

        declared = {expected["name"]: expected["why"]
                    for expected in declaration["expected_survivors"]}

        undeclared = [survivor for survivor in survivors if survivor not in declared]
        if undeclared:
            raise SweepRefused(
                f"{name}: undeclared survivors {undeclared}. A surviving mutant is an untested "
                "guard until somebody writes down why it cannot be tested")

        resurrected = [expected for expected in declared if expected not in survivors]
        if resurrected:
            raise SweepRefused(
                f"{name}: {resurrected} were declared as expected survivors and were KILLED. That "
                "is not a silent improvement: the coverage that justified them moved, and the "
                "declaration is now describing a repository that no longer exists")

        after = assert_tree_unchanged(before, _tree_manifest(root, tracked), name)

        return {
            "sweep_id": name,
            "target": target_name,
            "tests": tests,
            "mutants_declared": len(declaration["mutants"]),
            "killed": len(killed),
            "survivors": survivors,
            "expected_survivors": declared,
            "per_mutant": records,
            "baseline_passed": True,
            "working_tree_unchanged": True,
            "working_tree_sha256": _manifest_digest(after),
            "tree_manifest_exclusions": list(TREE_MANIFEST_EXCLUSIONS),
            "staged_copy_only": True,
            "record_is_not_evidence_of_correctness":
                "a killed mutant shows a guard is load-bearing, not that the guard is right",
        }
    finally:
        lock.unlink(missing_ok=True)
        if staging_root is None:
            shutil.rmtree(scratch, ignore_errors=True)


def main(argv):
    if len(argv) != 2:
        print("usage: python scripts/mutation_sweep.py <sweep_id>", file=sys.stderr)
        return 2
    result = run_sweep(argv[1])
    out = SWEEP_DIR / f"{argv[1]}.result.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{result['killed']}/{result['mutants_declared']} killed, "
          f"{len(result['survivors'])} survivors "
          f"({len(result['expected_survivors'])} declared)")
    print(f"written to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
