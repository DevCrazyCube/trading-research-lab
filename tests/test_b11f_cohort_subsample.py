"""Tests for the B11F cohort subsample -- the hash-on-mint uniform draw.

The preregistration (research/B11F_COHORT_SUBSAMPLE_PREREGISTRATION.json) makes two
promises this suite is built to enforce:

  (a) the selector reads creation-time identity ONLY -- never an activity quantity;
  (b) the pilot that SIZED N contains no selection machinery at all, so N could never have
      been tuned to include or exclude specific curves.

Test (b) is written so it FAILS when it should: alongside asserting the real pilot is clean,
it asserts a fabricated pilot carrying a hash helper is flagged. A pilot-isolation test that
passes on an empty check is worthless, so the check is proven non-vacuous here.
"""
import ast
import hashlib
import importlib.util
import pathlib
import sqlite3
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "b11f_cohort_subsample.py"
PILOT_DIR = ROOT / "research" / "b11f" / "pilot"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b11f = _load("b11f_cohort_subsample", SCRIPT)


def _synthetic_mints(count, tag="m"):
    # Deterministic, distinct, base58-ish mints; no seed dependence.
    return [f"{tag}{i:06d}pump" for i in range(count)]


def _write_fresh_cohort(path, members, *, start_slot=100, end_slot_exclusive=200,
                        contains_outcomes="0", artifact_kind="fresh_cohort_identity",
                        with_provenance=True, break_hash=False):
    """Fabricate a minimal artifact that b11d_cohort_adapter.assert_fresh_cohort accepts.

    Parameters let individual tests corrupt exactly one property (a wrong hash, a missing
    provenance row, an outcome claim) to prove the subsample refuses it.
    """
    adapter = b11f._load_adapter()
    con = sqlite3.connect(str(path))
    try:
        con.executescript("""
            CREATE TABLE cohort_identity (
                mint TEXT PRIMARY KEY, bonding_curve TEXT NOT NULL UNIQUE,
                launch_slot INTEGER NOT NULL, is_mayhem_mode INTEGER NOT NULL,
                create_signature TEXT NOT NULL);
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE provenance (
                source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                start_slot INTEGER NOT NULL, end_slot_exclusive INTEGER NOT NULL,
                slots_scanned INTEGER NOT NULL, slots_retrieved INTEGER NOT NULL,
                slots_skipped INTEGER NOT NULL, members INTEGER NOT NULL,
                cohort_sha256 TEXT NOT NULL);
            CREATE VIEW outcome AS
                SELECT mint, bonding_curve, launch_slot, is_mayhem_mode FROM cohort_identity;
        """)
        con.executemany(
            "INSERT INTO cohort_identity VALUES (?, ?, ?, ?, ?)",
            [(m["mint"], m["bonding_curve"], m["launch_slot"], m["is_mayhem_mode"],
              m["create_signature"]) for m in members])
        digest = adapter.cohort_digest(members)
        if break_hash:
            digest = "0" * 64
        con.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [
            ("schema_version", "1.0.0"),
            ("artifact_kind", artifact_kind),
            ("contains_outcomes", contains_outcomes),
            ("outcome_view_columns", "mint,bonding_curve,launch_slot,is_mayhem_mode"),
            ("cohort_sha256", digest),
            ("source_sha256", "0" * 64),
            ("start_slot", str(start_slot)),
            ("end_slot_exclusive", str(end_slot_exclusive)),
        ])
        if with_provenance:
            con.execute("INSERT INTO provenance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ("synthetic", "0" * 64, start_slot, end_slot_exclusive,
                         100, 100, 0, len(members), digest))
        con.commit()
    finally:
        con.close()


def _members(mints):
    return [{"mint": m, "bonding_curve": f"curve{i:06d}", "launch_slot": 100 + i,
             "is_mayhem_mode": i % 2, "create_signature": f"sig{i:06d}"}
            for i, m in enumerate(mints)]


class TheDrawIsDeterministicAndUniform(unittest.TestCase):
    def setUp(self):
        self.mints = _synthetic_mints(500)

    def test_same_inputs_same_output(self):
        self.assertEqual(b11f.selected(self.mints, n=100),
                         b11f.selected(self.mints, n=100))

    def test_does_not_depend_on_input_order(self):
        forward = b11f.selected(self.mints, n=100)
        reversed_ = b11f.selected(list(reversed(self.mints)), n=100)
        self.assertEqual(forward, reversed_)

    def test_selection_is_distinct_and_the_right_size(self):
        chosen = b11f.selected(self.mints, n=137)
        self.assertEqual(len(chosen), 137)
        self.assertEqual(len(set(chosen)), 137)
        self.assertTrue(set(chosen) <= set(self.mints))

    def test_a_changed_seed_changes_the_draw(self):
        # Same N, different seed -> different set (with overwhelming probability at this size).
        a = set(b11f.selected(self.mints, seed="seed-a", n=100))
        b = set(b11f.selected(self.mints, seed="seed-b", n=100))
        self.assertNotEqual(a, b)


class TheDrawIsNested(unittest.TestCase):
    def test_a_larger_n_is_a_superset_and_a_prefix(self):
        mints = _synthetic_mints(400)
        small = b11f.selected(mints, n=50)
        large = b11f.selected(mints, n=200)
        self.assertTrue(set(small) <= set(large))
        self.assertEqual(large[:50], small)  # prefix, not merely subset


class TheDrawRefusesRatherThanLie(unittest.TestCase):
    def test_empty_cohort_refuses(self):
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.selected([], n=1)

    def test_duplicate_mint_refuses(self):
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.selected(["a", "a", "b"], n=1)

    def test_n_larger_than_population_refuses_it_does_not_truncate(self):
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.selected(_synthetic_mints(10), n=11)

    def test_n_below_one_refuses(self):
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.selected(_synthetic_mints(10), n=0)

    def test_boolean_n_is_not_an_integer_count(self):
        # True is an int subclass; a size of "True" is a bug, not a request for one curve.
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.selected(_synthetic_mints(10), n=True)

    def test_empty_mint_in_the_cohort_refuses(self):
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.selection_key("")


# --- Test (a): the selector reads creation-time identity only -----------------------------

BANNED_ACTIVITY_SUBSTRINGS = (
    "signature", "trade", "graduat", "price", "reserve", "volume", "activity",
    "balance", "holder", "buy", "sell", "swap", "outcome",
)


def _identifiers_in(func_node):
    names = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


class TheSelectorReadsCreationTimeIdentityOnly(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(SCRIPT.read_text())

    def test_selection_key_signature_is_mint_and_seed(self):
        node = _func(self.tree, "selection_key")
        params = [a.arg for a in node.args.args]
        self.assertEqual(params, ["mint", "seed"])

    def test_selected_signature_is_mints_seed_and_n(self):
        node = _func(self.tree, "selected")
        params = [a.arg for a in node.args.args]
        self.assertEqual(params, ["cohort_mints", "seed", "n"])

    def test_no_activity_identifier_appears_in_the_selection_functions(self):
        for fname in ("selection_key", "selected"):
            identifiers = _identifiers_in(_func(self.tree, fname))
            for ident in identifiers:
                lowered = ident.lower()
                for banned in BANNED_ACTIVITY_SUBSTRINGS:
                    self.assertNotIn(
                        banned, lowered,
                        f"{fname} refers to {ident!r}, which reads as an activity/outcome "
                        f"quantity ({banned}); selection may key on creation identity only")

    def test_selection_key_free_names_are_a_creation_time_allowlist(self):
        # Free names (not the params, not locals) the function may reach. Anything outside
        # this list is an input the selector was never supposed to have.
        node = _func(self.tree, "selection_key")
        allowed = {"hashlib", "int", "isinstance", "str", "SubsampleRefused", "SEED"}
        params = {a.arg for a in node.args.args}
        assigned = {t.id for n in ast.walk(node) if isinstance(n, ast.Assign)
                    for t in n.targets if isinstance(t, ast.Name)}
        free = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} - params - assigned
        self.assertTrue(
            free <= allowed,
            f"selection_key reaches unexpected free names {free - allowed}; the selector must "
            "read only its inputs and hashing")


# --- Test (b): the pilot that sized N contains no selection machinery ----------------------

def pilot_selection_machinery(py_path):
    """Reasons a pilot module would be capable of deriving the hash order. Empty == clean.

    Scans CODE (the AST), not text: the README documents the property in prose and so
    legitimately contains the words 'sha256' and 'smallest'. Flags real machinery only --
    a hashlib import, an sha256/nsmallest reference, the frozen SEED literal, or a call into
    the selector itself.
    """
    reasons = []
    tree = ast.parse(pathlib.Path(py_path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ("hashlib", "heapq"):
                    reasons.append(f"imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in ("hashlib", "heapq"):
                reasons.append(f"imports from {node.module}")
        elif isinstance(node, ast.Attribute):
            if node.attr in ("sha256", "nsmallest", "sha512", "blake2b", "md5"):
                reasons.append(f"references {node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in ("sha256", "nsmallest", "selection_key", "selected"):
                reasons.append(f"references {node.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == b11f.SEED:
                reasons.append("contains the frozen selection SEED literal")
    return reasons


class ThePilotContainsNoSelectionMachinery(unittest.TestCase):
    def test_every_pilot_module_is_clean(self):
        modules = sorted(PILOT_DIR.glob("*.py"))
        self.assertTrue(modules, f"no pilot modules found under {PILOT_DIR}; disclosure "
                                 "references artifacts that are not there")
        for module in modules:
            self.assertEqual(
                pilot_selection_machinery(module), [],
                f"{module.name} carries selection machinery; if the pilot could derive the "
                "hash order, N could have been tuned to include or exclude specific curves")

    def test_the_check_flags_a_pilot_that_would_carry_machinery(self):
        # The non-vacuous half: a fabricated pilot with a hash helper MUST be flagged, or the
        # clean result above proves nothing.
        with tempfile.TemporaryDirectory() as tmp:
            planted = pathlib.Path(tmp) / "sneaky_pilot.py"
            planted.write_text(
                "import hashlib\n"
                "def rank(mint):\n"
                "    return int.from_bytes(hashlib.sha256(mint.encode()).digest(), 'big')\n")
            reasons = pilot_selection_machinery(planted)
            self.assertTrue(reasons, "the pilot-isolation check passed on a file that imports "
                                     "hashlib and calls sha256; it is vacuous")

    def test_the_check_flags_the_frozen_seed_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            planted = pathlib.Path(tmp) / "seed_pilot.py"
            planted.write_text(f"SEED = {b11f.SEED!r}\n")
            self.assertTrue(pilot_selection_machinery(planted))


# --- The artifact the collection gate will read -------------------------------------------

class TheSubsampleArtifactIsAFreshCohort(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.source = self.dir / "parent_cohort.sqlite"
        self.members = _members(_synthetic_mints(300))
        _write_fresh_cohort(self.source, self.members)

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_builds_an_artifact_the_gate_accepts_with_exactly_n_members(self):
        out = self.dir / "sub.sqlite"
        result = b11f.build_subsample(self.source, out, n=50)
        adapter = b11f._load_adapter()
        verified = adapter.assert_fresh_cohort(str(out))  # would raise if not a fresh cohort
        self.assertEqual(verified["members"], 50)
        self.assertEqual(result["n"], 50)

    def test_the_selected_rows_are_a_subset_of_the_parent(self):
        out = self.dir / "sub.sqlite"
        b11f.build_subsample(self.source, out, n=50)
        parent_mints = {m["mint"] for m in self.members}
        con = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
        try:
            sub_mints = {r[0] for r in con.execute("SELECT mint FROM cohort_identity")}
        finally:
            con.close()
        self.assertTrue(sub_mints <= parent_mints)
        self.assertEqual(sub_mints, set(b11f.selected(parent_mints, n=50)))

    def test_metadata_records_the_draw_for_audit(self):
        out = self.dir / "sub.sqlite"
        b11f.build_subsample(self.source, out, n=50)
        con = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
        try:
            meta = dict(con.execute("SELECT key, value FROM metadata"))
        finally:
            con.close()
        self.assertEqual(meta["subsample_seed"], b11f.SEED)
        self.assertEqual(meta["subsample_n"], "50")
        self.assertEqual(meta["subsample_population"], "300")
        self.assertTrue(meta["subsample_parent_cohort_sha256"])

    def test_it_is_deterministic_to_the_byte(self):
        a, b = self.dir / "a.sqlite", self.dir / "b.sqlite"
        b11f.build_subsample(self.source, a, n=50)
        b11f.build_subsample(self.source, b, n=50)
        # cohort hash is the identity-level determinism; row order is the byte-level one.
        con_a = sqlite3.connect(f"file:{a}?mode=ro", uri=True)
        con_b = sqlite3.connect(f"file:{b}?mode=ro", uri=True)
        try:
            rows_a = con_a.execute("SELECT mint FROM cohort_identity ORDER BY mint").fetchall()
            rows_b = con_b.execute("SELECT mint FROM cohort_identity ORDER BY mint").fetchall()
        finally:
            con_a.close(); con_b.close()
        self.assertEqual(rows_a, rows_b)

    def test_write_once_it_refuses_to_overwrite(self):
        out = self.dir / "sub.sqlite"
        b11f.build_subsample(self.source, out, n=50)
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.build_subsample(self.source, out, n=50)

    def test_a_parent_claiming_outcomes_is_refused(self):
        bad = self.dir / "bad.sqlite"
        _write_fresh_cohort(bad, self.members, contains_outcomes="1")
        out = self.dir / "sub.sqlite"
        with self.assertRaises(Exception):
            b11f.build_subsample(bad, out, n=50)

    def test_a_parent_with_no_provenance_window_is_refused(self):
        bad = self.dir / "noprov.sqlite"
        _write_fresh_cohort(bad, self.members, with_provenance=False)
        out = self.dir / "sub.sqlite"
        with self.assertRaises(b11f.SubsampleRefused):
            b11f.build_subsample(bad, out, n=50)

    def test_a_parent_whose_rows_do_not_match_its_hash_is_refused(self):
        bad = self.dir / "tampered.sqlite"
        _write_fresh_cohort(bad, self.members, break_hash=True)
        out = self.dir / "sub.sqlite"
        with self.assertRaises(Exception):
            b11f.build_subsample(bad, out, n=50)


if __name__ == "__main__":
    unittest.main()
