import collections
import importlib.util
import pathlib
import tempfile
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _isolation import IsolatedDashboard, digests, assert_production_untouched

ROOT = pathlib.Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dashboard", ROOT / "scripts" / "interactive_dashboard.py")
DASH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DASH)

RELEASED = "- **Status:** corrections applied; **ownership RELEASED**"


class DashboardTests(unittest.TestCase):
    def test_handoff_requires_terminal_status(self):
        active = ("## 2026-07-28 — Claude — subject\n"
                  "- **Seq:** 1\n"
                  "- **Status:** implementation ownership\n"
                  "- **Requested action:** wait")
        self.assertIsNone(DASH.handoff_target(active))

    def test_routes_released_entries_between_claudes(self):
        entry = ("## 2026-07-28 — Claude — done\n"
                 "- **Seq:** 2\n"
                 "- **Status:** review; ownership released\n"
                 "- **Requested action:** continue")
        self.assertEqual(DASH.handoff_target(entry, "claude1"), "claude2")
        self.assertEqual(DASH.handoff_target(entry, "claude2"), "claude1")

    def test_unowned_handoff_starts_with_claude1(self):
        entry = ("## 2026-07-28 — Claude — done\n"
                 "- **Seq:** 3\n"
                 "- **Status:** implementation + handoff\n"
                 "- **Requested action:** continue")
        self.assertEqual(DASH.handoff_target(entry, None), "claude1")


class HandoffRoutingRegressionTests(unittest.TestCase):
    """Pins the two defects recorded in agent_discussion.md Seq 63 and Seq 67.

    The original tests passed entries beginning with the '## ' heading - a string shape
    `latest_entry()` could never produce, because it sliced from the Seq line. Production
    routing was therefore dead while the suite stayed green. These tests exercise the shape
    `latest_entry()` actually returns.
    """

    def test_latest_entry_includes_the_author_heading(self):
        log = pathlib.Path(tempfile.mkdtemp()) / "discussion.md"
        log.write_text(
            "## 2026-07-28 — Codex — first\n"
            "- **Seq:** 1\n"
            "- **Status:** handoff\n"
            "\n"
            "## 2026-07-28 — Claude — second\n"
            "- **Seq:** 2\n"
            + RELEASED + "\n",
            encoding="utf-8")
        original, DASH.DISCUSSION = DASH.DISCUSSION, log
        try:
            sequence, entry = DASH.latest_entry()
        finally:
            DASH.DISCUSSION = original
        self.assertEqual(sequence, 2)
        self.assertTrue(entry.startswith("## 2026-07-28 — Claude — second"),
                        "entry must start at the heading, not at the Seq line")
        self.assertEqual(DASH.handoff_target(entry, "claude1"), "claude2",
                         "the shape latest_entry() returns must route")

    def test_routes_when_body_never_mentions_the_author(self):
        """The exact case the old body-text fallback failed.

        A released entry written in the first person, whose body contains no agent name.
        """
        entry = ("## 2026-07-28 — Claude — four corrections applied\n"
                 "- **Seq:** 66\n"
                 + RELEASED + "\n"
                 "- Applied the fixes and released ownership.\n")
        body = entry.split("\n", 1)[1].lower()
        self.assertNotIn("claude", body,
                         "fixture must not name the author outside the heading")
        self.assertEqual(DASH.handoff_target(entry, "claude1"), "claude2")
        self.assertEqual(DASH.handoff_target(entry, "claude2"), "claude1")
        self.assertEqual(DASH.handoff_target(entry, None), "claude1")

    def test_does_not_route_an_entry_whose_subject_merely_names_claude(self):
        """The old fallback would misroute this: another author, subject naming Claude."""
        entry = ("## 2026-07-28 — Codex — Claude should audit the artifact\n"
                 "- **Seq:** 63\n"
                 + RELEASED + "\n"
                 "- Claude should pick this up next.\n")
        self.assertIsNone(DASH.handoff_target(entry, "claude1"))
        self.assertIsNone(DASH.handoff_target(entry, None))

    def test_author_parsing_fails_closed(self):
        for heading in ("## no author field here", "## 2026-07-28", ""):
            entry = heading + "\n- **Seq:** 9\n" + RELEASED + "\n"
            self.assertIsNone(DASH.handoff_target(entry, "claude1"), repr(heading))

    def test_status_gate_still_required(self):
        entry = ("## 2026-07-28 — Claude — still working\n"
                 "- **Seq:** 5\n"
                 "- **Status:** implementation ownership\n")
        self.assertIsNone(DASH.handoff_target(entry, "claude1"))

    def test_entry_author_extracts_the_author_field_only(self):
        self.assertEqual(
            DASH.entry_author("## 2026-07-28 — Claude — subject naming Codex\n"), "claude")
        self.assertEqual(
            DASH.entry_author("## 2026-07-28 — Codex — subject naming Claude\n"), "codex")


class SendGuardTests(unittest.TestCase):
    """A dispatch that lands in a shell must fail loudly, not be recorded as delivered.

    `tmux send-keys` exits 0 whenever the pane exists, so tmux's return code cannot tell a
    delivered handoff from one typed into a shell prompt. supervisor.log carries evidence of
    that class of failure (a mangled 'd/usr/bin/python' line).
    """

    def setUp(self):
        self.calls = []
        self.originals = (DASH.tmux, DASH.pane_id, DASH.write_state)
        DASH.pane_id = lambda agent: "%15"
        DASH.write_state = lambda **kw: self.calls.append(("state", kw))

    def tearDown(self):
        DASH.tmux, DASH.pane_id, DASH.write_state = self.originals

    def _tmux_with_command(self, command):
        def fake(*args, capture=False, check=True):
            if args and args[0] == "display-message":
                return command
            self.calls.append(("tmux", args))
            return 0
        return fake

    def test_refuses_to_send_into_a_shell_prompt(self):
        for shell in ("zsh", "bash", "sh"):
            self.calls.clear()
            DASH.tmux = self._tmux_with_command(shell)
            with self.assertRaises(RuntimeError) as ctx:
                DASH.send("claude1", "handoff")
            self.assertIn("refusing", str(ctx.exception))
            self.assertEqual([c for c in self.calls if c[0] == "tmux"], [],
                             "must not send keys at all")
            self.assertEqual([c for c in self.calls if c[0] == "state"], [],
                             "must not record a delivery that did not happen")

    def test_refuses_when_the_pane_is_gone(self):
        DASH.tmux = self._tmux_with_command("")
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("claude1", "handoff")
        self.assertIn("gone", str(ctx.exception))
        self.assertEqual([c for c in self.calls if c[0] == "state"], [])

    def test_sends_and_records_when_an_agent_is_running(self):
        DASH.tmux = self._tmux_with_command("claude")
        DASH.send("claude1", "handoff")
        sends = [c for c in self.calls if c[0] == "tmux"]
        self.assertEqual(len(sends), 2, "literal text then Enter")
        state = [c for c in self.calls if c[0] == "state"]
        self.assertEqual(len(state), 1)
        self.assertEqual(state[0][1]["last_target"], "claude1")
        self.assertEqual(state[0][1]["last_send_pane_command"], "claude")

    def test_rejects_unknown_agent_before_touching_tmux(self):
        DASH.tmux = self._tmux_with_command("claude")
        with self.assertRaises(ValueError):
            DASH.send("claude3", "handoff")
        self.assertEqual(self.calls, [])


class SequenceAllocationTests(unittest.TestCase):
    """Pins the Seq-allocation race that produced four collisions in one session (75, 76, 83, 84)."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.saved = (DASH.RUNTIME, DASH.SEQ_LOCK, DASH.SEQ_COUNTER, DASH.DISCUSSION)
        DASH.RUNTIME = self.tmp
        DASH.SEQ_LOCK = self.tmp / "seq.lock"
        DASH.SEQ_COUNTER = self.tmp / "seq.counter"
        DASH.DISCUSSION = self.tmp / "discussion.md"
        DASH.DISCUSSION.write_text(
            "## d — Claude — a\n- **Seq:** 1\n- **Status:** handoff\n\n"
            "## d — Claude — b\n- **Seq:** 2\n- **Status:** handoff\n", encoding="utf-8")

    def tearDown(self):
        DASH.RUNTIME, DASH.SEQ_LOCK, DASH.SEQ_COUNTER, DASH.DISCUSSION = self.saved

    def test_allocations_do_not_repeat_before_entries_are_appended(self):
        """The core defect: serialising the read is not enough.

        An agent may compose for minutes between allocating and appending. If allocation only
        read the log, every allocation in that gap returns the same number.
        """
        got = [DASH.next_sequence() for _ in range(4)]
        self.assertEqual(got, [3, 4, 5, 6])
        self.assertEqual(len(set(got)), 4)

    def test_concurrent_allocation_yields_distinct_values(self):
        import threading
        out, lock = [], threading.Lock()

        def grab():
            value = DASH.next_sequence()
            with lock:
                out.append(value)

        threads = [threading.Thread(target=grab) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(out), 12)
        self.assertEqual(len(set(out)), 12, f"collisions under concurrency: {sorted(out)}")

    def test_counter_never_regresses_below_the_log(self):
        DASH.next_sequence()                                   # counter -> 3
        DASH.DISCUSSION.write_text(
            DASH.DISCUSSION.read_text() + "\n## d — Claude — c\n- **Seq:** 50\n", encoding="utf-8")
        self.assertEqual(DASH.next_sequence(), 51,
                         "a hand-written higher Seq must not be overwritten")

    def test_lock_is_released_even_when_allocation_fails(self):
        DASH.DISCUSSION.unlink()                               # force a read failure
        with self.assertRaises(Exception):
            DASH.next_sequence()
        self.assertFalse(DASH.SEQ_LOCK.exists(), "a leaked lock would wedge every later allocation")

    def test_stale_lock_times_out_with_an_actionable_message(self):
        DASH.SEQ_LOCK.write_text("99999")
        with self.assertRaises(RuntimeError) as ctx:
            DASH.next_sequence(timeout=0.2, poll=0.02)
        self.assertIn("stale lock", str(ctx.exception))
        DASH.SEQ_LOCK.unlink()

    def test_duplicate_detection_finds_collisions(self):
        text = ("## d — Claude — a\n- **Seq:** 7\n"
                "## d — Claude — b\n- **Seq:** 8\n"
                "## d — Claude — c\n- **Seq:** 7\n")
        self.assertEqual(DASH.duplicate_sequences(text), [7])
        self.assertEqual(DASH.duplicate_sequences("## d — Claude — a\n- **Seq:** 7\n"), [])

    def test_latest_entry_still_uses_file_order_not_maximum(self):
        """Regression guard: routing must keep taking the last entry in the file.

        Switching to max() would look tidier and would silently misroute whenever a renumbered
        entry carries a higher value than the genuinely newest one.
        """
        DASH.DISCUSSION.write_text(
            "## d — Claude — renumbered high\n- **Seq:** 99\n- **Status:** handoff\n\n"
            "## d — Claude 2 — actually newest\n- **Seq:** 3\n- **Status:** released\n",
            encoding="utf-8")
        sequence, entry = DASH.latest_entry()
        self.assertEqual(sequence, 3)
        self.assertIn("actually newest", entry.splitlines()[0])


class SeqNoteParsingTests(unittest.TestCase):
    """A renumbered entry carries a trailing note, and the parser must still see it.

    Requiring end-of-line straight after the digits made every collision fix in the log
    invisible: `all_sequences()` under-reported, `duplicate_sequences()` could not detect a
    duplicated renumber, and the log half of `next_sequence()`'s `max(log, counter)` missed the
    log's true maximum - defeating the stated guarantee that a hand-written entry cannot be
    silently overwritten.
    """

    NOTED = ("## d — Claude — renumbered\n"
             "- **Seq:** 94  _(collision fix: appended as a duplicate Seq 84; renumbered by its "
             "author. Physical position is authoritative for chronology.)_\n"
             "- **Status:** released\n")

    def setUp(self):
        # DASH.DISCUSSION points at the real agent_discussion.md. Any test writing to it
        # unpatched would destroy the log, so redirect it for the whole class.
        self.saved = DASH.DISCUSSION
        DASH.DISCUSSION = pathlib.Path(tempfile.mkdtemp()) / "discussion.md"

    def tearDown(self):
        DASH.DISCUSSION = self.saved

    def test_a_noted_seq_line_is_parsed(self):
        self.assertEqual(DASH.all_sequences(self.NOTED), [94])

    def test_noted_and_plain_lines_are_counted_together(self):
        text = self.NOTED + "\n## d — Claude 2 — plain\n- **Seq:** 95\n"
        self.assertEqual(DASH.all_sequences(text), [94, 95])

    def test_a_duplicated_renumber_is_detected(self):
        text = self.NOTED + "\n## d — Claude 2 — plain\n- **Seq:** 94\n"
        self.assertEqual(DASH.duplicate_sequences(text), [94],
                         "a collision involving a noted entry must not hide from check-seq")

    def test_digits_must_be_followed_by_whitespace_or_end_of_line(self):
        for bad in ("- **Seq:** 84x\n", "- **Seq:** 84_(note)_\n", "- **Seq:** v84\n"):
            self.assertEqual(DASH.all_sequences(bad), [], repr(bad))

    def test_trailing_whitespace_only_still_parses(self):
        self.assertEqual(DASH.all_sequences("- **Seq:** 84   \n"), [84])

    def test_latest_entry_resolves_an_entry_whose_seq_carries_a_note(self):
        DASH.DISCUSSION.write_text(
            "## d — Claude 2 — older\n- **Seq:** 3\n- **Status:** released\n\n" + self.NOTED,
            encoding="utf-8")
        sequence, entry = DASH.latest_entry()
        self.assertEqual(sequence, 94)
        self.assertIn("renumbered", entry.splitlines()[0])

    def test_every_seq_line_in_the_real_log_is_parsed(self):
        """The check that would have caught this, run against the log itself.

        A permissive scan and the strict parser must agree. If they ever diverge, some entry is
        invisible to allocation and duplicate detection - which is how six went unnoticed.
        """
        import re
        text = (ROOT / "agent_discussion.md").read_text(encoding="utf-8")
        permissive = [int(v) for v in re.findall(r"^- \*\*Seq:\*\* (\d+)", text, re.MULTILINE)]
        self.assertEqual(DASH.all_sequences(text), permissive)
        self.assertTrue(permissive, "the log must contain Seq lines for this test to mean anything")


class ProductionSafetyTests(unittest.TestCase):
    """The suite must never write to the untracked production files.

    `agent_discussion.md` and `DECISIONS.md` have no git backup — the whole `meme/` tree is
    gitignored and git tracks zero files under it. A fixture that overwrites one destroys project
    history outright. Seq 96 disclosed a near-miss of exactly this kind, caught only by reading
    the code before running it.
    """

    def test_dashboard_module_paths_point_at_real_files_by_default(self):
        # This is the hazard itself, asserted rather than assumed: the module's defaults are live
        # paths, so any unpatched test writes to production.
        self.assertTrue(str(DASH.DISCUSSION).endswith("agent_discussion.md"))
        self.assertTrue(DASH.DISCUSSION.exists(),
                        "the default DISCUSSION path is a real, existing file")

    def test_isolation_base_redirects_every_dashboard_path(self):
        class Probe(IsolatedDashboard):
            dash = DASH

            def runTest(self):  # noqa: N802
                pass

        probe = Probe()
        probe.setUp()
        try:
            for name in ("RUNTIME", "STATE", "LOG", "STOP", "DISCUSSION",
                         "SEQ_LOCK", "SEQ_COUNTER"):
                value = str(getattr(DASH, name))
                self.assertTrue(value.startswith(str(probe.tmp)),
                                f"{name} still points outside the sandbox: {value}")
        finally:
            probe.tearDown()
        self.assertTrue(str(DASH.DISCUSSION).endswith("agent_discussion.md"),
                        "tearDown must restore the real paths")

    def test_guard_detects_a_modified_protected_file(self):
        import tempfile as _t, pathlib as _p
        import _isolation
        fake = _p.Path(_t.mkdtemp()) / "protected.md"
        fake.write_text("original", encoding="utf-8")
        saved = _isolation.PROTECTED
        _isolation.PROTECTED = (fake,)
        try:
            before = _isolation.digests()
            fake.write_text("clobbered", encoding="utf-8")
            with self.assertRaises(AssertionError) as ctx:
                _isolation.assert_production_untouched(before)
            self.assertIn("no git backup", str(ctx.exception))
        finally:
            _isolation.PROTECTED = saved

    def test_guard_passes_when_nothing_is_touched(self):
        before = digests()
        assert_production_untouched(before, self)
        self.assertGreaterEqual(len(before), 5, "protected set should cover the core documents")


class FakeTmux:
    """Records every tmux call and simulates a pane that is not ready straight away.

    `shell_polls` is how many readiness checks report a shell with no prompt drawn yet;
    `app_polls` is how many report a shell after the launch command was typed. Both model the
    real race: tmux returns immediately, the pane is not listening yet.
    """

    def __init__(self, shell_polls=2, app_polls=3):
        self.calls = []
        self.shell_polls = collections.defaultdict(lambda: shell_polls)
        self.app_polls = collections.defaultdict(lambda: app_polls)
        self.launched = set()

    def __call__(self, *args, capture=False, check=True):
        self.calls.append(args)
        if args[0] == "has-session":
            return 1                                    # no session yet, so start() proceeds
        if args[0] == "display-message":
            pane = args[3]
            if args[4] == "#{pane_id}":
                return "%1"
            if pane in self.launched:                   # launch command has been typed
                if self.app_polls[pane] > 0:
                    self.app_polls[pane] -= 1
                    return "zsh"                        # app has not replaced the shell yet
                return "claude"
            return "zsh"
        if args[0] == "capture-pane":
            pane = args[3]
            if self.shell_polls[pane] > 0:
                self.shell_polls[pane] -= 1
                return ""                               # prompt not drawn yet
            return "user@host %"
        if args[0] == "split-window":
            return f"%{len(self.calls)}"
        if args[0] == "send-keys" and args[3] == "-l" and "claude -c" in args[4]:
            self.launched.add(args[2])
        return 0

    def sends_to(self, pane):
        return [a for a in self.calls if a[0] == "send-keys" and a[2] == pane]

    def index_of_first_send(self, pane):
        for i, a in enumerate(self.calls):
            if a[0] == "send-keys" and a[2] == pane:
                return i
        return None

    def index_of_prompt_ready(self, pane):
        """Index of the capture-pane call that first reported a drawn prompt."""
        seen = 0
        for i, a in enumerate(self.calls):
            if a[0] == "capture-pane" and a[3] == pane:
                seen += 1
                if seen > self.shell_polls.default_factory():
                    return i
        return None


class ReadinessWaitTests(IsolatedDashboard):
    """`tmux send-keys` is fire-and-forget: it exits 0 as soon as the pane exists.

    Typing into a pane whose shell has not initialised loses the leading characters, which is
    the `d/usr/bin/python` line in supervisor.log. These pin that nothing is typed before the
    pane is demonstrably listening, and that an unready pane fails loudly rather than silently.
    """

    dash = DASH

    def setUp(self):
        super().setUp()
        self.saved_tmux, self.saved_sleep = DASH.tmux, DASH.time.sleep
        DASH.time.sleep = lambda _s: None

    def tearDown(self):
        DASH.tmux, DASH.time.sleep = self.saved_tmux, self.saved_sleep
        super().tearDown()

    def test_wait_for_shell_blocks_until_the_prompt_is_drawn(self):
        fake = FakeTmux(shell_polls=3)
        DASH.tmux = fake
        self.assertEqual(DASH.wait_for_shell("%1"), "zsh")
        captures = [a for a in fake.calls if a[0] == "capture-pane"]
        self.assertEqual(len(captures), 4, "must keep polling while the pane is blank")

    def test_a_shell_that_never_draws_a_prompt_raises(self):
        DASH.tmux = FakeTmux(shell_polls=10 ** 6)
        with self.assertRaises(RuntimeError) as ctx:
            DASH.wait_for_shell("%1", timeout=0.0)
        self.assertIn("not listening", str(ctx.exception))

    def test_a_missing_pane_fails_immediately_rather_than_waiting_out_the_timeout(self):
        DASH.tmux = lambda *a, capture=False, check=True: "" if capture else 0
        with self.assertRaises(RuntimeError) as ctx:
            DASH.wait_for_pane("%9", lambda c, t: True, "anything", timeout=30.0)
        self.assertIn("gone", str(ctx.exception))

    def test_wait_for_app_waits_for_the_shell_to_be_replaced(self):
        fake = FakeTmux(shell_polls=0, app_polls=2)
        DASH.tmux = fake
        fake.launched.add("%1")
        self.assertEqual(DASH.wait_for_app("%1"), "claude")

    def test_wait_for_app_times_out_while_a_shell_persists(self):
        fake = FakeTmux(shell_polls=0, app_polls=10 ** 6)
        DASH.tmux = fake
        fake.launched.add("%1")
        with self.assertRaises(RuntimeError):
            DASH.wait_for_app("%1", timeout=0.0)


class StartOrderingTests(IsolatedDashboard):
    """The regression that produced the mangled supervisor line: keys sent before readiness."""

    dash = DASH

    def setUp(self):
        super().setUp()
        self.saved_tmux, self.saved_sleep = DASH.tmux, DASH.time.sleep
        DASH.time.sleep = lambda _s: None
        self.fake = FakeTmux()
        DASH.tmux = self.fake

    def tearDown(self):
        DASH.tmux, DASH.time.sleep = self.saved_tmux, self.saved_sleep
        super().tearDown()

    def test_nothing_is_typed_into_a_pane_before_its_prompt_is_drawn(self):
        DASH.start(None)
        panes = {a[2] for a in self.fake.calls if a[0] == "send-keys"}
        self.assertTrue(panes, "start() must send something")
        for pane in panes:
            ready = self.fake.index_of_prompt_ready(pane)
            first = self.fake.index_of_first_send(pane)
            self.assertIsNotNone(ready, f"{pane} was never polled for readiness")
            self.assertLess(ready, first,
                            f"keys were sent to {pane} before its prompt was drawn")

    def test_the_identity_prompt_waits_for_claude_to_replace_the_shell(self):
        """The poll must fall *between* the launch and the identity prompt.

        An earlier version of this test only checked that some readiness poll existed for the
        pane, which is true whether or not the fix is present - `wait_for_shell` polls the same
        way before the launch. It passed against a mutant with the wait removed. The window
        between the two sends is the only place the assertion means anything.
        """
        DASH.start(None)
        checked = 0
        for pane in {a[2] for a in self.fake.calls if a[0] == "send-keys"}:
            launch = self._index_of_send(pane, "claude -c")
            identity = self._index_of_send(pane, "You are Claude")
            if identity is None:
                continue
            self.assertIsNotNone(launch, f"{pane} got an identity prompt with no launch command")
            self.assertLess(launch, identity)
            between = [a for a in self.fake.calls[launch + 1:identity]
                       if a[0] == "display-message" and a[3] == pane
                       and a[4] == "#{pane_current_command}"]
            self.assertTrue(
                between,
                f"identity prompt for {pane} was typed with no readiness check after the launch; "
                f"it would land in the shell while Claude is still booting")
            checked += 1
        self.assertEqual(checked, 2, "both agent panes must be covered")

    def test_start_does_not_use_a_fixed_sleep_before_dispatching_to_an_agent(self):
        """The old `time.sleep(1); send(first, ...)` reliably tripped the Seq-73 shell guard."""
        slept = []
        DASH.time.sleep = slept.append
        DASH.start("claude1")
        self.assertEqual([s for s in slept if s >= 1], [],
                         "readiness must be polled, not slept through")
        literal = [a[4] for a in self.fake.calls
                   if a[0] == "send-keys" and len(a) > 4 and a[3] == "-l"]
        self.assertTrue(any("continue the latest active handoff" in text for text in literal),
                        "the first dispatch must still be delivered")

    def _index_of_send(self, pane, needle):
        for i, a in enumerate(self.fake.calls):
            if a[0] == "send-keys" and a[2] == pane and len(a) > 4 and needle in a[4]:
                return i
        return None


class UpgradeExistingOrderingTests(IsolatedDashboard):
    """`upgrade_existing()` respawns a pane and types into it, so it carries the same race.

    A respawned shell is no more ready than a newly created one; tmux returning from
    `respawn-pane` says nothing about whether zsh can accept input yet.
    """

    dash = DASH

    def setUp(self):
        super().setUp()
        self.saved = (DASH.tmux, DASH.time.sleep)
        DASH.time.sleep = lambda _s: None
        self.calls = []
        self.blank_captures = 2

        def fake(*args, capture=False, check=True):
            self.calls.append(args)
            if args[0] == "has-session":
                return 0
            if args[0] == "list-panes":
                return ("%1\tclaude1\tclaude\n"
                        "%2\tclaude2\tzsh\n"          # not running an agent: triggers respawn
                        "%3\tcontrol\tzsh")
            if args[0] == "capture-pane":
                if self.blank_captures > 0:
                    self.blank_captures -= 1
                    return ""
                return "user@host %"
            if args[0] == "display-message":
                return "claude" if self.respawn_done() else "zsh"
            return 0

        DASH.tmux = fake

    def respawn_done(self):
        """True once the launch command has been typed into the respawned pane."""
        return any(a[0] == "send-keys" and len(a) > 4 and "claude -c" in a[4]
                   for a in self.calls)

    def tearDown(self):
        DASH.tmux, DASH.time.sleep = self.saved
        super().tearDown()

    def test_respawned_pane_is_not_typed_into_before_its_prompt_is_drawn(self):
        DASH.upgrade_existing()
        respawn = next(i for i, a in enumerate(self.calls) if a[0] == "respawn-pane")
        first_send = next(i for i, a in enumerate(self.calls)
                          if a[0] == "send-keys" and a[2] == "%2")
        captures = [i for i, a in enumerate(self.calls)
                    if a[0] == "capture-pane" and respawn < i < first_send]
        self.assertTrue(captures,
                        "keys were typed into the respawned pane with no readiness check")


if __name__ == "__main__":
    unittest.main()
