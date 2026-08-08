"""Tests for the collection dashboard. It renders; it must never participate."""
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("collection_tui", ROOT / "scripts" / "collection_tui.py")
T = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(T)


class ItObservesAndNeverParticipates(unittest.TestCase):
    def test_the_module_names_no_write(self):
        source = (ROOT / "scripts" / "collection_tui.py").read_text()
        for forbidden in ("write_text(", "os.replace(", "shutil.", "executemany(", "INSERT ",
                          "UPDATE ", "DELETE "):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_every_sqlite_open_is_read_only(self):
        source = (ROOT / "scripts" / "collection_tui.py").read_text()
        self.assertIn("mode=ro", source)
        self.assertEqual(source.count("sqlite3.connect"), source.count("mode=ro"),
                         "every connect must carry mode=ro, or one of them can write")

    def test_it_is_not_manifest_pinned(self):
        spec = importlib.util.spec_from_file_location("b11c", ROOT / "scripts" / "b11c_maturity_watcher.py")
        b11c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b11c)
        self.assertNotIn("scripts/collection_tui.py", b11c.MANIFEST_FILES,
                         "pinning a display would let an edit to a progress bar quarantine a run")


class ItCannotShowAStageListThePipelineDoesNotHave(unittest.TestCase):
    def test_run_order_is_derived_from_the_supervisor(self):
        """A restated copy drifts. It did, twice tonight, one layer apart."""
        self.assertEqual(list(T.RUN_ORDER), list(T._b11c().RUN_ORDER))

    def test_the_source_does_not_restate_the_stage_names(self):
        source = (ROOT / "scripts" / "collection_tui.py").read_text()
        body = source.split("RUN_ORDER = _b11c().RUN_ORDER", 1)[1]
        self.assertNotIn('"simulator_replay_gate"', body,
                         "a literal stage name after the derivation is a copy waiting to drift")


class ItRendersWithoutTheWorld(unittest.TestCase):
    def test_a_missing_state_file_renders_rather_than_raising(self):
        original = T.STATE
        T.STATE = pathlib.Path("/nonexistent/state.json")
        self.addCleanup(setattr, T, "STATE", original)
        frame = T.render({})
        self.assertTrue(frame)
        self.assertTrue(any("B11A COLLECTION" in line for line in frame))

    def test_a_zero_total_bar_does_not_divide_by_zero(self):
        drawn, fraction = T.bar(0, 0)
        self.assertEqual(fraction, 0.0)
        self.assertIn("░", drawn)

    def test_a_bar_cannot_exceed_full(self):
        _, fraction = T.bar(500, 100)
        self.assertEqual(fraction, 1.0)

    def test_the_endpoint_is_never_rendered(self):
        """A TUI is tempting to feed raw state. The endpoint carries the credential in its path."""
        frame = "\n".join(T.render({}))
        state = T.read_state()
        endpoint = state.get("endpoint")
        if endpoint:
            self.assertNotIn(endpoint, frame)
        self.assertNotIn("http", frame.lower().replace("https://api.telegram.org", ""))


if __name__ == "__main__":
    unittest.main()
