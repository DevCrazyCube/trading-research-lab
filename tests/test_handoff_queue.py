import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

from tests._isolation import IsolatedDashboard

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "queue_dashboard", ROOT / "scripts" / "interactive_dashboard.py")
DASH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DASH)


class HandoffQueueTests(IsolatedDashboard):
    dash = DASH

    def test_handoff_persists_payload_and_uniquely_marked_audit(self):
        message_id, seq, target = DASH.create_handoff("claude", "Audit this", "Verify every guard.")
        self.assertEqual(target, "codex")
        row = DASH.queue_status()["messages"][0]
        self.assertEqual((row["id"], row["state"]), (message_id, "queued"))
        audit = DASH.DISCUSSION.read_text()
        self.assertIn(f"- **Seq:** {seq}", audit)
        self.assertEqual(audit.count(f"- **Handoff-ID:** {message_id}"), 1)

    def insert_prepared(self, message_id, seq, state="preparing", target="claude"):
        db = DASH.queue_connect()
        digest = DASH.hashlib.sha256(b"body").hexdigest()
        db.execute(
            "INSERT INTO handoff(id,created_at,sender,target,subject,payload,payload_sha256,"
            "audit_seq,state) VALUES(?,?,?,?,?,?,?,?,?)",
            (message_id, time.time(), "codex" if target == "claude" else "claude", target,
             f"subject {message_id}", "body", digest, seq, state))
        row = db.execute("SELECT * FROM handoff WHERE id=?", (message_id,)).fetchone()
        db.close()
        return row

    def test_a_later_id_does_not_mask_an_earlier_ones_audit_entry(self):
        """`- **Handoff-ID:** 1` is a SUBSTRING of `- **Handoff-ID:** 12`.

        Without a delimiter, `_append_audit_once` read a later entry as proof the earlier one had
        been written. Recovering a handoff interrupted while `preparing` then flipped it to
        `queued` -- delivering it -- while writing NO audit entry. Reproduced end-to-end before the
        trailing newline was added to the marker.
        """
        DASH._append_audit_once(self.insert_prepared(12, 12, state="queued"))
        self.insert_prepared(1, 1)
        self.assertEqual(DASH.recover_preparing(), 1)
        audit = DASH.DISCUSSION.read_text()
        self.assertIn("- **Handoff-ID:** 1\n", audit,
                      "id 1 must get its own entry even though id 12 is already logged")
        self.assertIn("- **Handoff-ID:** 12\n", audit)
        db = DASH.queue_connect()
        self.assertEqual(
            db.execute("SELECT state FROM handoff WHERE id=1").fetchone()["state"], "queued")
        db.close()

    def test_a_preparing_handoff_cannot_be_acknowledged(self):
        """Its audit entry does not exist yet; acknowledging it delivers an unlogged handoff."""
        self.insert_prepared(5, 5)
        with self.assertRaises(RuntimeError) as ctx:
            DASH.receive_handoff("claude", 5)
        self.assertIn("still preparing", str(ctx.exception))
        DASH.recover_preparing()
        row = DASH.receive_handoff("claude", 5)
        self.assertEqual(row["id"], 5)

    def test_re_acknowledging_is_idempotent_and_keeps_the_first_timestamp(self):
        """A re-sent notification must not error, and must not rewrite the original ack time."""
        self.insert_prepared(6, 6)
        DASH.recover_preparing()
        DASH.receive_handoff("claude", 6)
        db = DASH.queue_connect()
        first = db.execute("SELECT acknowledged_at FROM handoff WHERE id=6").fetchone()[0]
        db.close()
        time.sleep(0.01)
        DASH.receive_handoff("claude", 6)
        db = DASH.queue_connect()
        again = db.execute("SELECT acknowledged_at FROM handoff WHERE id=6").fetchone()[0]
        db.close()
        self.assertEqual(first, again)

    def test_recovery_finishes_preparing_record_once(self):
        db = DASH.queue_connect()
        digest = DASH.hashlib.sha256(b"body").hexdigest()
        db.execute(
            "INSERT INTO handoff(created_at,sender,target,subject,payload,payload_sha256,"
            "audit_seq,state) VALUES(?,?,?,?,?,?,?,'preparing')",
            (time.time(), "codex", "claude", "subject", "body", digest, 9))
        db.close()
        self.assertEqual(DASH.recover_preparing(), 1)
        self.assertEqual(DASH.recover_preparing(), 0)
        self.assertEqual(DASH.DISCUSSION.read_text().count("- **Handoff-ID:** 1"), 1)
        self.assertEqual(DASH.queue_status()["messages"][0]["state"], "queued")

    def test_receive_is_target_bound_and_is_the_only_delivery_proof(self):
        message_id, _, _ = DASH.create_handoff("codex", "subject", "immutable task")
        with self.assertRaisesRegex(RuntimeError, "addressed to claude"):
            DASH.receive_handoff("codex", message_id)
        self.assertEqual(DASH.queue_status()["messages"][0]["state"], "queued")
        row = DASH.receive_handoff("claude", message_id)
        self.assertEqual(row["payload"], "immutable task")
        self.assertEqual(DASH.queue_status()["messages"][0]["state"], "acknowledged")

    def test_oldest_unacknowledged_message_blocks_later_notification(self):
        first, _, _ = DASH.create_handoff("codex", "one", "first")
        second, _, _ = DASH.create_handoff("claude", "two", "second")
        seen = []
        saved = DASH.pane_id, DASH.pane_command, DASH.agent_busy, DASH.composer_text, DASH.send_line
        DASH.pane_id = lambda agent: "%1"
        DASH.pane_command = lambda pane: "claude"
        DASH.agent_busy = lambda pane: False
        DASH.composer_text = lambda pane: ""
        DASH.send_line = lambda pane, text: seen.append(text)
        try:
            db = DASH.queue_connect()
            DASH.notify_next(db)
            db.close()
        finally:
            (DASH.pane_id, DASH.pane_command, DASH.agent_busy,
             DASH.composer_text, DASH.send_line) = saved
        self.assertIn(f"HANDOFF {first}", seen[0])
        self.assertNotIn(f"HANDOFF {second}", seen[0])

    def test_staged_matching_notification_gets_enter_not_a_second_copy(self):
        message_id, _, _ = DASH.create_handoff("claude", "one", "first")
        db = DASH.queue_connect()
        db.execute("UPDATE handoff SET state='notified',last_notified_at=? WHERE id=?",
                   (time.time(), message_id))
        calls = []
        saved = DASH.pane_id, DASH.composer_text, DASH.tmux, DASH.send_line
        DASH.pane_id = lambda agent: "%1"
        DASH.composer_text = lambda pane: (
            f"HANDOFF {message_id}: run python scripts/interactive_dashboard.py receive codex "
            f"{message_id}")
        DASH.tmux = lambda *args, **kwargs: calls.append(args) or 0
        DASH.send_line = lambda *args: self.fail("must not retype a staged notification")
        try:
            self.assertTrue(DASH.notify_next(db))
        finally:
            DASH.pane_id, DASH.composer_text, DASH.tmux, DASH.send_line = saved
            db.close()
        self.assertEqual(calls, [("send-keys", "-t", "%1", "Enter")])


class TmuxTimeoutTests(IsolatedDashboard):
    dash = DASH

    # Long enough that a correctly-bounded call must give up first, short enough that a REGRESSION
    # fails instead of hanging: an unbounded `tmux()` waits this out and returns success, so the
    # assertions below fail on their own. A `sleep 600` fake would instead wedge the suite -- the
    # same defect these tests exist to catch.
    SLOW_TMUX_SECONDS = 4

    def use_hanging_tmux(self, seconds):
        """Put a `tmux` on PATH that outlasts the dashboard's patience, and bound that patience."""
        fake_bin = self.tmp / "bin"
        fake_bin.mkdir(exist_ok=True)
        hanging = fake_bin / "tmux"
        hanging.write_text(f"#!/bin/sh\nsleep {self.SLOW_TMUX_SECONDS}\n")
        hanging.chmod(0o755)
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = f"{fake_bin}{os.pathsep}{saved_path}"
        self.addCleanup(lambda: os.environ.__setitem__("PATH", saved_path))
        saved = DASH.TMUX_TIMEOUT_SECONDS
        DASH.TMUX_TIMEOUT_SECONDS = seconds
        self.addCleanup(lambda: setattr(DASH, "TMUX_TIMEOUT_SECONDS", saved))

    def test_a_hanging_tmux_command_fails_instead_of_freezing_the_supervisor(self):
        """`tmux()` called `subprocess.run` with no timeout, so it waited forever.

        A tmux server that is down, starting, or wedged froze the supervisor inside its own main
        loop -- the loop that writes the heartbeat. It therefore stopped dispatching handoffs and
        stopped recording that it had stopped: `status` reported the stale heartbeat with no error
        anywhere. Confirmed by faulthandler traceback, blocked in `tmux` -> `subprocess.run` ->
        `communicate`, reached from `announce_protocol` -> `pane_id` -> `live_panes`.
        """
        self.use_hanging_tmux(0.5)
        started = time.monotonic()
        with self.assertRaises(RuntimeError) as ctx:
            DASH.tmux("list-panes")
        self.assertIn("did not return", str(ctx.exception))
        self.assertLess(time.monotonic() - started, self.SLOW_TMUX_SECONDS,
                        "the call was not bounded: it waited for tmux instead of giving up")

    def test_a_timed_out_tmux_call_reports_a_code_when_the_caller_asked_for_one(self):
        """`check=False` callers read a returncode; they must not get an exception instead."""
        self.use_hanging_tmux(0.5)
        self.assertEqual(DASH.tmux("has-session", "-t", "nope", check=False),
                         DASH.TMUX_TIMEOUT_RETURNCODE)
        self.assertFalse(DASH.has_session(), "a timed-out probe must not report a live session")


class RealTmuxDeliveryTests(IsolatedDashboard):
    dash = DASH

    def setUp(self):
        super().setUp()
        self.socket = f"dashboard-test-{os.getpid()}-{time.time_ns()}"
        self.saved_socket, DASH.TMUX_SOCKET = DASH.TMUX_SOCKET, self.socket

    def tearDown(self):
        subprocess.run(["tmux", "-L", self.socket, "kill-server"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        DASH.TMUX_SOCKET = self.saved_socket
        super().tearDown()

    def test_compact_notification_is_submitted_with_enter_then_acknowledged(self):
        fake = self.tmp / "codex"
        shutil.copy2("/bin/cat", fake)
        fake.chmod(0o755)
        session = "queue-e2e"
        DASH.SESSION = session
        self.addCleanup(lambda: setattr(DASH, "SESSION", "meme-agents"))
        DASH.tmux("new-session", "-d", "-s", session, str(fake))
        pane = DASH.tmux("display-message", "-p", "-t", session, "#{pane_id}", capture=True)
        DASH.tag_pane(pane, "codex")
        DASH.write_state(mode="auto", panes={"codex": pane})
        message_id, _, _ = DASH.create_handoff("claude", "real tmux", "execute bounded task")
        db = DASH.queue_connect()
        self.assertTrue(DASH.notify_next(db))
        db.close()
        deadline = time.time() + 3
        captured = ""
        while time.time() < deadline and f"HANDOFF {message_id}" not in captured:
            captured = DASH.tmux("capture-pane", "-p", "-t", pane, capture=True)
            time.sleep(0.05)
        self.assertIn(f"HANDOFF {message_id}", captured)
        self.assertEqual(DASH.queue_status()["messages"][0]["state"], "notified")
        DASH.receive_handoff("codex", message_id)
        self.assertEqual(DASH.queue_status()["messages"][0]["state"], "acknowledged")


class SupervisorProcessTests(IsolatedDashboard):
    dash = DASH

    def supervisor_env(self):
        env = os.environ.copy()
        env.update({
            "DASHBOARD_RUNTIME": str(self.tmp),
            "DASHBOARD_DISCUSSION": str(DASH.DISCUSSION),
            "DASHBOARD_ROOT": str(ROOT),
            "DASHBOARD_INTERVAL": "0.05",
            "DASHBOARD_SESSION": DASH.SESSION,
            "DASHBOARD_TMUX_SOCKET": DASH.TMUX_SOCKET,
            "DASHBOARD_TMUX_TIMEOUT": "2",
        })
        return env

    def test_a_rejected_second_supervisor_does_not_cancel_a_pending_stop(self):
        """`STOP.unlink()` used to run BEFORE the singleton check.

        So an unrelated `run` attempt deleted the STOP file on its way to being rejected, and the
        shutdown that an operator had just requested of the LIVE supervisor was silently lost. The
        lock is held here directly rather than by starting a real supervisor, so the ordering is
        tested without racing a loop that exits as soon as it sees STOP.
        """
        lock = (self.tmp / "supervisor.lock").open("a+")
        self.addCleanup(lock.close)
        DASH.fcntl.flock(lock, DASH.fcntl.LOCK_EX | DASH.fcntl.LOCK_NB)
        stop = self.tmp / "STOP"
        stop.touch()
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "interactive_dashboard.py"), "run"],
            env=self.supervisor_env(), capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("singleton lock", result.stderr)
        self.assertTrue(stop.exists(), "a rejected start must not cancel a pending shutdown")

    def test_second_supervisor_is_rejected_and_restart_recovers(self):
        env = os.environ.copy()
        env.update({
            "DASHBOARD_RUNTIME": str(self.tmp),
            "DASHBOARD_DISCUSSION": str(DASH.DISCUSSION),
            "DASHBOARD_ROOT": str(ROOT),
            "DASHBOARD_INTERVAL": "0.05",
            # Without these the child supervisor targets the LIVE meme-agents session: its
            # protocol_notice table is sandboxed and therefore empty, so it re-announces the
            # protocol into the real Codex and Claude panes, and the resulting per-iteration
            # error printing at 20 Hz fills the stdout pipe and hangs this test.
            "DASHBOARD_SESSION": DASH.SESSION,
            "DASHBOARD_TMUX_SOCKET": DASH.TMUX_SOCKET,
        })
        command = [sys.executable, str(ROOT / "scripts" / "interactive_dashboard.py"), "run"]
        first = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True)
        try:
            deadline = time.time() + 4
            healthy = False
            while time.time() < deadline:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "interactive_dashboard.py"), "status"],
                    env=env, capture_output=True, text=True)
                if result.returncode == 0 and json.loads(result.stdout)["supervisor"]["healthy"]:
                    healthy = True
                    break
                time.sleep(0.05)
            self.assertTrue(healthy)
            # The timeout is the point of this line. `supervisor_loop` opened the lock file and
            # then ran `try: pass` -- no flock at all -- so `except BlockingIOError` was dead code
            # and the second supervisor started normally instead of being rejected. With no
            # timeout, `subprocess.run` waited on a process designed never to exit and the whole
            # suite hung here with no failure message. A regression must fail, not hang.
            try:
                second = subprocess.run(command, env=env, capture_output=True, text=True,
                                        timeout=30)
            except subprocess.TimeoutExpired:
                self.fail("a second supervisor kept running: the singleton lock is not held")
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("singleton lock", second.stderr)
        finally:
            (self.tmp / "STOP").touch()
            first.wait(timeout=5)
            first.communicate()
        (self.tmp / "STOP").unlink(missing_ok=True)
        restarted = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 4
            while time.time() < deadline:
                status = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "interactive_dashboard.py"), "status"],
                    env=env, capture_output=True, text=True)
                if status.returncode == 0 and json.loads(status.stdout)["supervisor"]["healthy"]:
                    break
                time.sleep(0.05)
            else:
                self.fail("restarted supervisor never established a healthy heartbeat")
        finally:
            (self.tmp / "STOP").touch()
            restarted.wait(timeout=5)
            restarted.communicate()
