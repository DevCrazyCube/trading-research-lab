"""Guards over research/COMPONENT_INVENTORY.json, so a readiness component cannot go unlisted.

WHY THIS FILE EXISTS
--------------------
The B17c gap map asserted that the recorder and the operator surface did not exist. Both do:
`scripts/recorder.py` with `tests/test_recorder.py` and 21 MB of B6 evidence, and
`ui/operator_console.html` with `scripts/b12b_operator_snapshot.py`,
`scripts/b12b_preview_server.py` and `tests/test_b12b_operator_console.py`. The gap map was prose,
and prose drifts from the filesystem silently.

So the inventory is data now, and these tests are the thing that makes it honest. The sweep is the
important one: it discovers candidates from disk rather than from a list somebody remembered to
update, so a new component matching a readiness marker fails the suite until it is classified. A
guard that only checks the entries already written could never have caught the omission it exists
to prevent.
"""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "research" / "COMPONENT_INVENTORY.json"
GAP_MAP_PATH = ROOT / "research" / "B17C_SHADOW_READINESS_GAP_MAP.md"

# The five files B17c wrongly declared absent. Named individually and permanently: this exact
# mistake gets its own guard, because it was made once and the cost was a peer having to catch it.
WRONGLY_DECLARED_ABSENT = (
    "scripts/recorder.py",
    "tests/test_recorder.py",
    "ui/operator_console.html",
    "scripts/b12b_operator_snapshot.py",
    "scripts/b12b_preview_server.py",
)

SWEPT_DIRECTORIES = ("scripts", "ui")

# The markers live HERE, not in the inventory, and that placement is the point. The first version
# read them out of COMPONENT_INVENTORY.json -- the very file the sweep polices -- so emptying the
# list disarmed the guard and nothing failed. A mutation caught it. A guard whose sensitivity is
# configured by its subject is not a guard; the inventory now has to MATCH this list instead of
# defining it.
NAME_MARKERS = ("recorder", "operator", "console", "preview", "capture", "wallet", "treasury",
                "execut")

# Phrases that assert an absence. A document may use them, but not about a path that exists.
ABSENCE_PHRASES = ("does not exist", "do not exist", "no operator surface", "does not yet exist")


def _inventory():
    return json.loads(INVENTORY_PATH.read_text())


class InventoryIntegrityTests(unittest.TestCase):

    def setUp(self):
        self.inventory = _inventory()
        self.components = self.inventory["components"]
        self.paths = {entry["path"] for entry in self.components}

    def test_every_listed_component_exists_on_disk(self):
        """A phantom entry is the same defect in the other direction."""
        for entry in self.components:
            with self.subTest(path=entry["path"]):
                self.assertTrue((ROOT / entry["path"]).exists(),
                                f"{entry['path']} is inventoried but not on disk")

    def test_every_component_has_a_recognised_status(self):
        allowed = set(self.inventory["status_values"])
        for entry in self.components:
            with self.subTest(path=entry["path"]):
                self.assertIn(entry["status"], allowed)

    def test_the_five_files_b17c_wrongly_called_absent_are_all_listed(self):
        """The specific regression. These exist; no inventory may omit them again."""
        for path in WRONGLY_DECLARED_ABSENT:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists(), f"{path} vanished from disk")
                self.assertIn(path, self.paths, f"{path} exists but is not in the inventory")

    def test_none_of_those_five_is_recorded_as_absent(self):
        """Listing a file and then calling it absent would satisfy the letter and miss the point."""
        for entry in self.components:
            if entry["path"] in WRONGLY_DECLARED_ABSENT:
                with self.subTest(path=entry["path"]):
                    self.assertNotEqual(entry["status"], "ABSENT")

    def test_the_sweep_finds_no_unclassified_readiness_component(self):
        """Discovery from disk, not from memory. This is the guard that would have caught B17c.

        Any file under scripts/ or ui/ whose name carries a readiness marker must be classified,
        even if the classification is NOT_A_READINESS_COMPONENT. Silence is not an answer.
        """
        markers = NAME_MARKERS
        unclassified = []
        for directory in SWEPT_DIRECTORIES:
            for path in sorted((ROOT / directory).rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue  # build output, not a component
                relative = path.relative_to(ROOT).as_posix()
                name = path.name.lower()
                if any(marker in name for marker in markers) and relative not in self.paths:
                    unclassified.append(relative)
        self.assertEqual(unclassified, [],
                         f"readiness components exist but are unclassified: {unclassified}. "
                         f"Add them to {INVENTORY_PATH.name} with a status.")

    def test_the_inventory_documents_the_same_markers_the_sweep_uses(self):
        """The inventory may describe the markers; it may not quietly narrow them.

        Without this, the two could drift and a reader of the JSON would believe a wider sweep runs
        than actually does.
        """
        self.assertEqual(tuple(self.inventory["name_markers_the_guard_sweeps_for"]), NAME_MARKERS)

    def test_absence_claims_carry_their_evidence(self):
        """An absence asserted without a named verification is an assumption wearing a status."""
        for entry in self.inventory["verified_absent"]:
            with self.subTest(what=entry["what"]):
                self.assertEqual(entry["status"], "ABSENT")
                self.assertTrue(entry.get("absence_evidence", "").strip(),
                                "an absence must name how it was verified")

    def test_the_kill_switch_really_has_no_writer(self):
        """Re-verify the one absence I still claim, rather than trusting the document.

        `kill_switch_engaged` may be READ and DISPLAYED anywhere; what must not exist is a component
        that assigns it outside a test fixture or the b17a counterexample.
        """
        assignment = re.compile(r"""\[["']kill_switch_engaged["']\]\s*=|kill_switch_engaged\s*=\s*""")
        writers = []
        for path in sorted((ROOT / "scripts").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative == "scripts/b17a_shadow_rehearsal.py":
                continue  # the kill-switch counterexample sets it deliberately
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#") or '"kill_switch_engaged":' in stripped:
                    continue  # a dict literal field, and comments, are not assignments
                if assignment.search(stripped):
                    writers.append(f"{relative}:{number}")
        self.assertEqual(writers, [],
                         f"something now writes the kill switch: {writers}. If that is an operator "
                         f"control, the inventory's ABSENT entry is stale and must be corrected.")


class GapMapConsistencyTests(unittest.TestCase):
    """The gap map is prose, so it gets checked against the data rather than trusted."""

    def setUp(self):
        self.text = GAP_MAP_PATH.read_text()
        self.inventory = _inventory()

    def test_the_gap_map_never_calls_an_existing_component_absent(self):
        """The literal B17c defect, as a test.

        A line may say 'does not exist' about something that truly does not. It may not say it on a
        line that also names a path present on disk.

        QUOTED text is exempt, and must be: the correction table in §0 reproduces the original false
        claims verbatim in order to correct them. That is the same prose-versus-code distinction the
        execution-surface scan makes -- a phrase in quotation marks is being REPORTED, not asserted,
        and a guard that cannot tell the difference forbids documenting your own mistakes.
        """
        present = {entry["path"] for entry in self.inventory["components"]
                   if (ROOT / entry["path"]).exists()}
        quoted = re.compile(r'"[^"]*"')
        offences = []
        for number, line in enumerate(self.text.splitlines(), start=1):
            lowered = quoted.sub("", line).lower()
            if not any(phrase in lowered for phrase in ABSENCE_PHRASES):
                continue
            for path in present:
                if path in line:
                    offences.append(f"line {number}: absence claimed about {path}")
        self.assertEqual(offences, [], f"the gap map contradicts the filesystem: {offences}")

    def test_the_gap_map_names_the_components_it_previously_missed(self):
        """A correction that removes a false claim without naming what was missed teaches nobody."""
        for path in WRONGLY_DECLARED_ABSENT:
            with self.subTest(path=path):
                self.assertIn(path, self.text,
                              f"{path} exists and the gap map does not mention it")

    def test_the_gap_map_points_at_the_inventory(self):
        self.assertIn("COMPONENT_INVENTORY.json", self.text)


if __name__ == "__main__":
    unittest.main()
