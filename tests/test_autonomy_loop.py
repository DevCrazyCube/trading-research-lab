import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("autonomy", ROOT / "scripts" / "autonomy_loop.py")
AUTONOMY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTONOMY)


class AutonomyLoopTests(unittest.TestCase):
    def test_handoff_must_alternate(self):
        good = {"status": "handoff", "summary": "done", "next_agent": "claude",
                "user_question": ""}
        self.assertEqual(AUTONOMY.validate_result(good, "codex"), good)
        bad = dict(good, next_agent="codex")
        with self.assertRaises(ValueError):
            AUTONOMY.validate_result(bad, "codex")

    def test_state_write_is_atomic_and_preserves_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = pathlib.Path(directory)
            with mock.patch.object(AUTONOMY, "RUNTIME", runtime), \
                 mock.patch.object(AUTONOMY, "STATE", runtime / "state.json"):
                AUTONOMY.write_state(status="running", turn=1)
                AUTONOMY.write_state(status="blocked", reason="test")
                state = json.loads((runtime / "state.json").read_text())
                self.assertEqual(state["status"], "blocked")
                self.assertEqual(state["turn"], 1)

    def test_codex_command_receives_structured_output_path(self):
        command = AUTONOMY.command_for("codex", "prompt", pathlib.Path("result.json"))
        self.assertEqual(command[0:2], ["codex", "exec"])
        self.assertIn("result.json", command)
        self.assertNotIn("-a", command)
        self.assertIn("sandbox_workspace_write.network_access=true", command)

    def test_owner_message_is_injected_and_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = pathlib.Path(directory)
            inbox = runtime / "inbox"
            archive = runtime / "archive"
            with mock.patch.object(AUTONOMY, "INBOX", inbox), \
                 mock.patch.object(AUTONOMY, "ARCHIVE", archive):
                AUTONOMY.control_message("build the simulator")
                messages = AUTONOMY.pending_messages()
                self.assertEqual(messages[0][1], "build the simulator")
                self.assertIn("build the simulator", AUTONOMY.prompt("codex", 1, 3, messages))
                AUTONOMY.archive_messages(messages)
                self.assertFalse(list(inbox.glob("*.json")))
                self.assertEqual(len(list(archive.glob("*.json"))), 1)

    def test_interrupt_without_active_process_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(AUTONOMY, "ACTIVE_PID", pathlib.Path(directory) / "pid"):
                self.assertEqual(AUTONOMY.interrupt_active(), 1)

    def test_status_marks_dead_running_process_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / "state.json"
            state.write_text('{"status":"running","supervisor_pid":99999999}')
            with mock.patch.object(AUTONOMY, "STATE", state):
                self.assertEqual(AUTONOMY.status_payload()["status"], "stale")


if __name__ == "__main__":
    unittest.main()
