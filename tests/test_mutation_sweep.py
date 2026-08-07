"""Guards for the mutation-sweep framework.

The framework's entire value is that its refusals are real, so every refusal here is provoked
rather than reasoned about. A sweep runner whose guards cannot fire is the exact thing it was
built to stop: an artefact reporting a clean number it did not earn.

The run-level guards are driven against a TINY SYNTHETIC GIT REPOSITORY rather than this one. That
keeps them fast enough to live in the default suite, and it means the tests exercise the real
staging path — `git ls-files`, copy, subprocess pytest — instead of a mock of it. `git add` alone
is enough, because `git ls-files` reads the index and no commit is needed.

No network, and nothing under the real working tree is written.
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


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SWEEP = load("mutation_sweep", "mutation_sweep.py")

TOY_SOURCE = '''\
def check(value):
    if value < 0:
        raise ValueError("negative")
    if value > 1000:
        raise ValueError("enormous")
    return value
'''

TOY_TEST = '''\
import importlib.util, pathlib, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("toy", ROOT / "scripts" / "toy.py")
TOY = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TOY)


class ToyTests(unittest.TestCase):
    def test_a_negative_is_refused(self):
        with self.assertRaises(ValueError):
            TOY.check(-1)

    def test_an_ordinary_value_passes(self):
        self.assertEqual(TOY.check(3), 3)
'''

# `if value > 1000` has no test on purpose: mutating it must SURVIVE, which is how the
# undeclared-survivor and declared-survivor guards get something real to react to.
KILLED_MUTANT = {"name": "negative guard neutered",
                 "old": "    if value < 0:", "new": "    if False:"}
SURVIVING_MUTANT = {"name": "enormous guard neutered",
                    "old": "    if value > 1000:", "new": "    if False:"}


def toy_repo(case, toy_source=TOY_SOURCE, toy_test=TOY_TEST):
    root = pathlib.Path(tempfile.mkdtemp(prefix="toy-repo-"))
    case.addCleanup(shutil.rmtree, root, True)
    (root / "scripts").mkdir()
    (root / "tests").mkdir()
    (root / "scripts" / "toy.py").write_text(toy_source)
    (root / "tests" / "test_toy.py").write_text(toy_test)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True,
                   capture_output=True)
    return root


def declaration(case, root, mutants, expected_survivors=(), sweep_id="toy", target=None):
    sweep_dir = root / "research" / "mutation"
    sweep_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "sweep_id": sweep_id,
        "target": target if target is not None else "scripts/toy.py",
        "tests": ["tests/test_toy.py"],
        "mutants": list(mutants),
        "expected_survivors": list(expected_survivors),
    }
    (sweep_dir / f"{sweep_id}.sweep.json").write_text(json.dumps(body))
    return sweep_dir


class DeclarationTests(unittest.TestCase):
    """A declaration must say enough that its result can be disbelieved."""

    def base(self):
        return {"sweep_id": "toy", "target": "scripts/toy.py", "tests": ["tests/test_toy.py"],
                "mutants": [dict(KILLED_MUTANT)], "expected_survivors": []}

    def test_each_required_field_is_individually_required(self):
        for field in ("sweep_id", "target", "tests", "mutants", "expected_survivors"):
            with self.subTest(field=field):
                body = self.base()
                del body[field]
                with self.assertRaisesRegex(SWEEP.SweepRefused, "does not state"):
                    SWEEP.assert_declaration(body, "toy")

    def test_a_declaration_that_does_not_know_its_own_name_refuses(self):
        body = self.base()
        body["sweep_id"] = "something_else"
        with self.assertRaisesRegex(SWEEP.SweepRefused, "calls itself"):
            SWEEP.assert_declaration(body, "toy")

    def test_a_sweep_with_no_mutants_refuses(self):
        """The whole-file version of a check that cannot fire: it would report a perfect score."""
        body = self.base()
        body["mutants"] = []
        with self.assertRaisesRegex(SWEEP.SweepRefused, "declares no mutants"):
            SWEEP.assert_declaration(body, "toy")

    def test_a_mutant_that_replaces_its_pattern_with_itself_refuses(self):
        body = self.base()
        body["mutants"] = [{"name": "inert", "old": "x", "new": "x"}]
        with self.assertRaisesRegex(SWEEP.SweepRefused, "with itself"):
            SWEEP.assert_declaration(body, "toy")

    def test_duplicate_mutant_names_refuse(self):
        body = self.base()
        body["mutants"] = [dict(KILLED_MUTANT), dict(KILLED_MUTANT)]
        with self.assertRaisesRegex(SWEEP.SweepRefused, "both called"):
            SWEEP.assert_declaration(body, "toy")

    def test_each_mutant_field_is_individually_required(self):
        for field in ("name", "old", "new"):
            with self.subTest(field=field):
                body = self.base()
                mutant = dict(KILLED_MUTANT)
                del mutant[field]
                body["mutants"] = [mutant]
                with self.assertRaisesRegex(SWEEP.SweepRefused, "does not state"):
                    SWEEP.assert_declaration(body, "toy")

    def test_a_declared_survivor_without_a_justification_refuses(self):
        body = self.base()
        body["expected_survivors"] = [{"name": KILLED_MUTANT["name"]}]
        with self.assertRaisesRegex(SWEEP.SweepRefused, "does not state 'why'"):
            SWEEP.assert_declaration(body, "toy")

    def test_a_declared_survivor_naming_no_mutant_refuses(self):
        """A stale declaration would silence a real survivor that later takes the same name."""
        body = self.base()
        body["expected_survivors"] = [{"name": "long gone", "why": "used to exist"}]
        with self.assertRaisesRegex(SWEEP.SweepRefused, "not one of the mutants"):
            SWEEP.assert_declaration(body, "toy")

    def test_an_unknown_declaration_field_refuses(self):
        """b12a's rule, here: a misspelled field is an absent field wearing a plausible name."""
        body = self.base()
        body["targets"] = ["scripts/toy.py"]
        with self.assertRaisesRegex(SWEEP.SweepRefused, "unknown field"):
            SWEEP.assert_declaration(body, "toy")

    def test_an_unknown_mutant_field_refuses(self):
        """The dangerous case: a pattern spelled into a field the sweep never reads is inert.

        `{"name": ..., "old": ..., "new": ..., "find": "..."}` applies whatever `old` says and
        counts as one applied mutant, while its author believes `find` did something. An inert
        mutant inflates the score exactly like a skipped one.
        """
        body = self.base()
        body["mutants"] = [dict(KILLED_MUTANT, find="text that appears nowhere")]
        with self.assertRaisesRegex(SWEEP.SweepRefused, "unknown field"):
            SWEEP.assert_declaration(body, "toy")

    def test_an_unknown_declared_survivor_field_refuses(self):
        body = self.base()
        body["expected_survivors"] = [
            {"name": KILLED_MUTANT["name"], "why": "reason", "becuase": "typo"}]
        with self.assertRaisesRegex(SWEEP.SweepRefused, "unknown field"):
            SWEEP.assert_declaration(body, "toy")

    def test_the_documentation_fields_are_permitted(self):
        """The allowlist has to admit the prose fields, or it forbids explaining a sweep."""
        body = self.base()
        body["description"] = "what this sweep is for"
        body["expected_survivors_note"] = "why there are none"
        body["mutants"] = [dict(KILLED_MUTANT, note="why this guard matters")]
        self.assertIs(SWEEP.assert_declaration(body, "toy"), body)

    def test_a_missing_declaration_file_refuses(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        with self.assertRaisesRegex(SWEEP.SweepRefused, "no sweep declaration"):
            SWEEP.load_sweep("absent", directory)


class RunTests(unittest.TestCase):
    """The guards that need a real sweep to fire."""

    def test_a_clean_sweep_kills_its_mutant_and_leaves_the_tree_alone(self):
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])
        before = (root / "scripts" / "toy.py").read_text()

        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

        self.assertEqual(result["killed"], 1)
        self.assertEqual(result["survivors"], [])
        self.assertTrue(result["baseline_passed"])
        self.assertTrue(result["working_tree_unchanged"])
        self.assertEqual((root / "scripts" / "toy.py").read_text(), before)

    def test_the_result_records_the_first_failing_test(self):
        """Not just that a mutant died. A mutant killed by a guard other than the one it names
        looks identical to one killed correctly, and a binary outcome cannot tell them apart."""
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])

        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

        record = result["per_mutant"][0]
        self.assertEqual(record["outcome"], "killed")
        self.assertIsNotNone(record["first_failing_test"], "the killing test was not recorded")
        self.assertIn("test_a_negative_is_refused", record["first_failing_test"])

    def test_a_surviving_mutant_records_no_failing_test(self):
        root = toy_repo(self)
        sweep_dir = declaration(
            self, root, [SURVIVING_MUTANT],
            [{"name": SURVIVING_MUTANT["name"], "why": "no test covers the enormous branch"}])

        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

        self.assertEqual(result["per_mutant"][0]["outcome"], "survived")
        self.assertIsNone(result["per_mutant"][0]["first_failing_test"])

    def test_the_field_records_the_FIRST_failure_not_the_responsible_guard(self):
        """Pins the limitation so the field is never re-read as something it cannot answer.

        `-x` stops at the first failure and unittest orders alphabetically within a class, so when
        several guards each kill a mutant this records whichever sorts first. Both seats verified
        that on a real case: b18a's tip mutant is recorded against
        `test_a_non_nullable_field_may_not_be_null` while
        `test_no_unmeasured_field_was_defaulted_to_zero_or_false` kills it just as independently.
        An audit built on the old reading produced 21 suspects that were almost all this artifact.

        Here THREE tests fail under the mutant and only the first in run order is recorded. Run
        order turns out to be class position then method order, not alphabetical across classes,
        which is a further reason the field cannot be read as "the guard responsible": the winner
        is decided by where a test sits in a file.
        """
        two_killers = TOY_TEST + '''

class BothCatchIt(unittest.TestCase):
    def test_aaa_also_rejects_a_negative(self):
        with self.assertRaises(ValueError):
            TOY.check(-5)

    def test_zzz_also_rejects_a_negative(self):
        with self.assertRaises(ValueError):
            TOY.check(-7)
'''
        root = toy_repo(self, toy_test=two_killers)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])

        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

        recorded = result["per_mutant"][0]["first_failing_test"]
        self.assertIn("test_a_negative_is_refused", recorded)
        # The other two kill it just as independently and are invisible in the record. That is
        # the whole limitation, asserted rather than described.
        self.assertNotIn("aaa", recorded)
        self.assertNotIn("zzz", recorded)

    def test_the_killing_test_is_parsed_from_real_pytest_output(self):
        self.assertEqual(
            SWEEP.first_failing_test(
                "FAILED tests/test_toy.py::ToyTests::test_a_negative_is_refused - AssertionError"),
            "tests/test_toy.py::ToyTests::test_a_negative_is_refused")
        self.assertIsNone(SWEEP.first_failing_test("2 passed in 0.01s"))

    def test_a_subtest_failure_is_parsed_too(self):
        """This project has 3,242 subtests, and pytest reports those as SUBFAILED.

        Matching only FAILED returned no killer for every mutant a subtest killed — the same
        defect the field exists to expose, one level down.
        """
        self.assertEqual(
            SWEEP.first_failing_test(
                "SUBFAILED(field='status') tests/test_toy.py::ToyTests::test_each_field - Error"),
            "tests/test_toy.py::ToyTests::test_each_field")

    def test_a_killed_mutant_with_an_unparsable_killer_reports_a_reason_not_null(self):
        """Null means "no killer", which is what a survivor reports.

        Collapsing "we could not tell what killed it" into that is the zero-standing-in-for-an-
        unknown failure under a different name, so it carries a reason code instead.
        """
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])
        real = SWEEP.first_failing_test
        SWEEP.first_failing_test = lambda _output: None
        self.addCleanup(setattr, SWEEP, "first_failing_test", real)

        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

        record = result["per_mutant"][0]
        self.assertEqual(record["outcome"], "killed")
        self.assertEqual(record["first_failing_test"], "U_KILLER_NOT_PARSED")

    def test_an_unmatched_pattern_refuses_rather_than_skipping(self):
        """A skipped mutant silently inflates the score, and the score is the whole product."""
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [
            {"name": "stale after a refactor", "old": "    if value < -999:", "new": "    if False:"}])
        with self.assertRaisesRegex(SWEEP.SweepRefused, "never applied"):
            SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

    def test_a_failing_baseline_refuses_instead_of_reporting_a_perfect_score(self):
        broken = TOY_TEST + '''

class BrokenTests(unittest.TestCase):
    def test_this_fails(self):
        self.assertEqual(1, 2)
'''
        root = toy_repo(self, toy_test=broken)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])
        with self.assertRaisesRegex(SWEEP.SweepRefused, "unmutated suite does not pass"):
            SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

    def test_an_undeclared_survivor_refuses(self):
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [SURVIVING_MUTANT])
        with self.assertRaisesRegex(SWEEP.SweepRefused, "undeclared survivors"):
            SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

    def test_a_declared_survivor_is_accepted_with_its_justification(self):
        root = toy_repo(self)
        sweep_dir = declaration(
            self, root, [SURVIVING_MUTANT],
            [{"name": SURVIVING_MUTANT["name"], "why": "no test covers the enormous branch"}])

        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

        self.assertEqual(result["survivors"], [SURVIVING_MUTANT["name"]])
        self.assertIn(SURVIVING_MUTANT["name"], result["expected_survivors"])

    def test_a_declared_survivor_that_gets_killed_refuses(self):
        """Not a silent improvement: the coverage that justified it moved."""
        root = toy_repo(self)
        sweep_dir = declaration(
            self, root, [KILLED_MUTANT],
            [{"name": KILLED_MUTANT["name"], "why": "claimed to be covered elsewhere"}])
        with self.assertRaisesRegex(SWEEP.SweepRefused, "declared as expected survivors and were"):
            SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

    def test_an_untracked_target_refuses(self):
        """A reader could not reproduce a sweep over a file that is not in the repository."""
        root = toy_repo(self)
        (root / "scripts" / "untracked.py").write_text("x = 1\n")
        sweep_dir = declaration(self, root, [KILLED_MUTANT], target="scripts/untracked.py")
        with self.assertRaisesRegex(SWEEP.SweepRefused, "not tracked by git"):
            SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)

    def test_the_staged_copy_is_what_gets_mutated(self):
        """The structural claim, checked: the mutation happens under the staging root."""
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])
        staging = pathlib.Path(tempfile.mkdtemp(prefix="staging-"))
        self.addCleanup(shutil.rmtree, staging, True)

        SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120, staging_root=staging)

        staged_target = staging / "tree" / "scripts" / "toy.py"
        self.assertTrue(staged_target.is_file(), "the sweep did not stage the target at all")
        self.assertEqual(staged_target.read_text(), (root / "scripts" / "toy.py").read_text(),
                         "the staged copy was left mutated")


class StagingTests(unittest.TestCase):
    def test_staging_copies_tracked_files_and_not_ignored_ones(self):
        root = toy_repo(self)
        (root / "scripts" / "ignored_artifact.bin").write_text("huge")
        destination = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, destination, True)

        SWEEP.stage_tree(destination, root)

        self.assertTrue((destination / "scripts" / "toy.py").is_file())
        self.assertTrue((destination / "tests" / "test_toy.py").is_file())
        self.assertFalse((destination / "scripts" / "ignored_artifact.bin").exists())


class ExtractedGuardTests(unittest.TestCase):
    """The two guards that no correct run can trigger.

    They were extracted from inline positions precisely so these tests can exist. Inline, their
    conditions are always false: a sweep builds the staged path itself and a correct sweep never
    touches the working tree. That made them checks that could not fire — protection in appearance
    only, and invisible to a mutation sweep because no test could tell the difference.
    """

    def test_a_target_escaping_the_staging_root_refuses(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        with self.assertRaisesRegex(SWEEP.SweepRefused, "escapes the staging root"):
            SWEEP.assert_within(root.parent / "elsewhere" / "victim.py", root, "toy")

    def test_a_target_inside_the_staging_root_is_returned(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        inside = root / "scripts" / "toy.py"
        self.assertEqual(SWEEP.assert_within(inside, root, "toy"), inside)

    def test_a_changed_working_tree_refuses_and_names_the_paths(self):
        """The first version could only say "something did", which cost its reader the diagnosis.

        The claude seat hit this refusal for real during a nine-minute sweep and had to hash every
        tracked file by hand to find that the cause was two files I had edited underneath them.
        """
        before = {"a.py": "1", "gone.py": "9", "same.py": "5"}
        after = {"a.py": "2", "new.py": "7", "same.py": "5"}
        with self.assertRaises(SWEEP.SweepRefused) as caught:
            SWEEP.assert_tree_unchanged(before, after, "toy")
        message = str(caught.exception)
        self.assertIn("a.py", message)
        self.assertIn("new.py", message)
        self.assertIn("gone.py", message)
        self.assertNotIn("same.py", message)

    def test_an_unchanged_working_tree_passes(self):
        manifest = {"a.py": "1"}
        self.assertEqual(SWEEP.assert_tree_unchanged(manifest, dict(manifest), "toy"), manifest)


class TreeManifestExclusionTests(unittest.TestCase):
    """The exclusion has to be narrow, and "narrow" is only a claim until something checks it."""

    def test_the_exclusion_list_is_exactly_the_coordination_log(self):
        self.assertEqual(SWEEP.TREE_MANIFEST_EXCLUSIONS, ("agent_discussion.md",))

    def test_a_handoff_during_a_sweep_does_not_trip_the_tree_check(self):
        """The dashboard appends to agent_discussion.md on every handoff.

        Without this exception, sending a colleague a message during a sweep destroys the sweep,
        which makes the collaboration protocol and the guard mutually exclusive.
        """
        root = toy_repo(self)
        log = root / "agent_discussion.md"
        log.write_text("initial\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        tracked = SWEEP.tracked_files(root)

        before = SWEEP._tree_manifest(root, tracked)
        log.write_text("initial\na handoff landed mid-sweep\n")
        after = SWEEP._tree_manifest(root, tracked)

        self.assertEqual(SWEEP.assert_tree_unchanged(before, after, "toy"), after)

    def test_a_change_to_anything_else_still_refuses(self):
        """The half that keeps the exception from becoming a hole."""
        root = toy_repo(self)
        tracked = SWEEP.tracked_files(root)
        before = SWEEP._tree_manifest(root, tracked)
        (root / "scripts" / "toy.py").write_text(TOY_SOURCE + "\n# edited\n")
        after = SWEEP._tree_manifest(root, tracked)

        with self.assertRaisesRegex(SWEEP.SweepRefused, "toy.py"):
            SWEEP.assert_tree_unchanged(before, after, "toy")


class SweepLockTests(unittest.TestCase):
    """Two sweeps at once collided before this existed, and blamed the staging root for it."""

    def test_a_second_sweep_refuses_immediately_while_one_holds_the_lock(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        SWEEP.acquire_lock(directory, "first")
        with self.assertRaisesRegex(SWEEP.SweepRefused, "another sweep holds the lock"):
            SWEEP.acquire_lock(directory, "second")

    def test_the_lock_names_the_holder_and_says_how_to_clear_it(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        SWEEP.acquire_lock(directory, "first")
        with self.assertRaises(SWEEP.SweepRefused) as caught:
            SWEEP.acquire_lock(directory, "second")
        message = str(caught.exception)
        self.assertIn("sweep=first", message)
        self.assertIn(str(os.getpid()), message)
        self.assertIn("delete", message)

    def test_a_completed_sweep_releases_its_lock(self):
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])
        SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)
        self.assertFalse((sweep_dir / ".sweep.lock").exists())

    def test_a_refused_sweep_also_releases_its_lock(self):
        """A lock left behind by a failure would block every later sweep."""
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [
            {"name": "stale", "old": "    if value < -999:", "new": "    if False:"}])
        with self.assertRaises(SWEEP.SweepRefused):
            SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120)
        self.assertFalse((sweep_dir / ".sweep.lock").exists())

    def test_the_lock_is_untracked_so_it_cannot_trip_the_tree_check(self):
        root = toy_repo(self)
        sweep_dir = root / "research" / "mutation"
        sweep_dir.mkdir(parents=True, exist_ok=True)
        SWEEP.acquire_lock(sweep_dir, "first")
        self.addCleanup((sweep_dir / ".sweep.lock").unlink, True)
        self.assertNotIn(".sweep.lock", " ".join(SWEEP.tracked_files(root)))


class GitAncestryStagingTests(unittest.TestCase):
    """Some components refuse a parameter that cannot be shown to have been committed first.

    `b11c` raises `Q03_git_ancestry_broken` — "a parameter with no history is a parameter nobody
    can show was frozen first" — so its tests fail in a tracked-file copy for a reason that has
    nothing to do with any mutant. That is the guard working, not a gap, and it made 45 of the 124
    staged-tree failures.
    """

    def test_a_tracked_only_tree_has_no_history(self):
        root = toy_repo(self)
        destination = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, destination, True)
        SWEEP.stage_tree(destination, root)
        self.assertFalse((destination / ".git").exists())

    def test_include_git_stages_the_history(self):
        root = toy_repo(self)
        destination = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, destination, True)
        SWEEP.stage_tree(destination, root, include_git=True)
        self.assertTrue((destination / ".git").is_dir())

    def test_history_is_COPIED_not_symlinked(self):
        """A symlink would put the real object store within reach of a mutated program."""
        root = toy_repo(self)
        destination = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, destination, True)
        SWEEP.stage_tree(destination, root, include_git=True)
        staged_git = destination / ".git"
        self.assertFalse(staged_git.is_symlink())
        for path in staged_git.rglob("*"):
            with self.subTest(path=path.name):
                self.assertFalse(path.is_symlink())

    def test_asking_for_history_that_does_not_exist_refuses(self):
        """The reachable case is a SUBDIRECTORY of a repository, not a directory outside one.

        Outside a repo, `git ls-files` fails first and staging never gets as far as this guard.
        Inside a subdirectory it succeeds — the subdirectory is tracked — while `.git` sits a level
        up and is absent. Writing this test the naive way produced a CalledProcessError instead of
        the refusal, which is how the reachable shape was found.
        """
        root = toy_repo(self)
        subdirectory = root / "scripts"
        self.assertTrue(SWEEP.tracked_files(subdirectory), "expected git to work in a subdirectory")
        self.assertFalse((subdirectory / ".git").exists())
        destination = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, destination, True)
        with self.assertRaisesRegex(SWEEP.SweepRefused, "no .git"):
            SWEEP.stage_tree(destination, subdirectory, include_git=True)

    def test_the_declaration_field_is_off_by_default(self):
        """Turning it on silently would change what every existing sweep's baseline sees."""
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])
        staging = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, staging, True)
        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120,
                                 staging_root=staging)
        self.assertIs(result["git_ancestry_staged"], False)
        self.assertFalse((staging / "tree" / ".git").exists())

    def test_a_declaration_may_ask_for_it(self):
        root = toy_repo(self)
        sweep_dir = declaration(self, root, [KILLED_MUTANT])
        body = json.loads((sweep_dir / "toy.sweep.json").read_text())
        body["needs_git_ancestry"] = True
        (sweep_dir / "toy.sweep.json").write_text(json.dumps(body))
        staging = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, staging, True)

        result = SWEEP.run_sweep("toy", root=root, sweep_dir=sweep_dir, timeout=120,
                                 staging_root=staging)

        self.assertIs(result["git_ancestry_staged"], True)
        self.assertTrue((staging / "tree" / ".git").is_dir())


class LiveCollectionIsUnreachableTests(unittest.TestCase):
    """The safety property that lets any of this run beside a live watcher.

    Staging copies git-TRACKED files. The live collection artifacts are untracked by design, so
    they are absent from a staged tree structurally rather than by anyone remembering to exclude
    them. This asserts that against the real repository, because it is the assumption every sweep
    in this project has been running on.
    """

    def test_the_live_watcher_artifacts_are_untracked_and_so_never_stage(self):
        tracked = set(SWEEP.tracked_files(ROOT))
        live = ["research/b11a/b11a_creates.sqlite",
                "research/b11a/b11a_creates.sqlite-wal",
                "research/b11a/supervisor_state.json",
                "research/b11a/supervisor.lock"]
        for path in live:
            with self.subTest(path=path):
                self.assertNotIn(path, tracked,
                                 f"{path} is tracked, so a sweep would stage a live artifact")

    def test_what_does_stage_from_that_path_is_historical_only(self):
        staged = [p for p in SWEEP.tracked_files(ROOT) if p.startswith("research/b11a/")]
        self.assertTrue(staged, "expected the historical incident records to be tracked")
        for path in staged:
            with self.subTest(path=path):
                self.assertRegex(path, r"^research/b11a/(incidents|superseded)/")


class ShippedSweepTests(unittest.TestCase):
    """The declarations that ship with the repository must be well-formed without running them.

    Running them here would put a nine-minute sweep in a seven-minute suite, which is the trade the
    framework's docstring explicitly refuses. Validating the declaration is cheap and catches the
    realistic decay: a mutant pattern that no longer matches after a refactor.
    """

    def test_every_shipped_declaration_is_well_formed(self):
        for path in sorted(SWEEP.SWEEP_DIR.glob("*.sweep.json")):
            with self.subTest(sweep=path.name):
                name = path.name[: -len(".sweep.json")]
                declaration_body = SWEEP.load_sweep(name)
                self.assertEqual(declaration_body["sweep_id"], name)

    def test_every_shipped_mutant_still_matches_its_target(self):
        """The decay that would otherwise turn a real sweep into a silent no-op."""
        for path in sorted(SWEEP.SWEEP_DIR.glob("*.sweep.json")):
            name = path.name[: -len(".sweep.json")]
            body = SWEEP.load_sweep(name)
            source = (ROOT / body["target"]).read_text()
            for mutant in body["mutants"]:
                with self.subTest(sweep=name, mutant=mutant["name"]):
                    self.assertIn(mutant["old"], source)

    def test_every_shipped_target_and_test_path_exists(self):
        for path in sorted(SWEEP.SWEEP_DIR.glob("*.sweep.json")):
            name = path.name[: -len(".sweep.json")]
            body = SWEEP.load_sweep(name)
            with self.subTest(sweep=name):
                self.assertTrue((ROOT / body["target"]).is_file())
                for test_path in body["tests"]:
                    self.assertTrue((ROOT / test_path).is_file())


if __name__ == "__main__":
    unittest.main()
