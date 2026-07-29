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


LAUNCH_MARKERS = ("codex --no-alt-screen", "claude --permission-mode")
"""Substring identifying the agent launch command in a `send-keys` call.

Defined once because it was previously written out three times as the literal `"claude -c"`, and
when the launch command legitimately changed — dropping `-c` so each agent starts a fresh named
session — all three broke at once for a reason that had nothing to do with what they assert. A
detail three tests depend on and none of them own is a detail that belongs in one place.
"""


class DashboardTests(unittest.TestCase):
    def test_codex_launch_command_is_the_owner_selected_command(self):
        self.assertEqual(
            DASH.agent_command("codex"),
            "codex --no-alt-screen -C /home/anont/meme -a never -s workspace-write "
            "-c sandbox_workspace_write.network_access=true "
            "-c check_for_update_on_startup=false")

    def test_handoff_requires_terminal_status(self):
        active = ("## 2026-07-28 — Claude — subject\n"
                  "- **Seq:** 1\n"
                  "- **Status:** implementation ownership\n"
                  "- **Requested action:** wait")
        self.assertIsNone(DASH.handoff_target(active))

    def test_routes_released_claude_entry_to_codex(self):
        entry = ("## 2026-07-28 — Claude — done\n"
                 "- **Seq:** 2\n"
                 "- **Status:** review; ownership released\n"
                 "- **Requested action:** continue")
        self.assertEqual(DASH.handoff_target(entry, "codex"), "codex")
        self.assertEqual(DASH.handoff_target(entry, "claude"), "codex")

    def test_unowned_handoff_starts_with_codex(self):
        entry = ("## 2026-07-28 — Claude — done\n"
                 "- **Seq:** 3\n"
                 "- **Status:** implementation + handoff\n"
                 "- **Requested action:** continue")
        self.assertEqual(DASH.handoff_target(entry, None), "codex")


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
        self.assertEqual(DASH.handoff_target(entry, "codex"), "codex",
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
        self.assertEqual(DASH.handoff_target(entry, "codex"), "codex")
        self.assertEqual(DASH.handoff_target(entry, "claude"), "codex")
        self.assertEqual(DASH.handoff_target(entry, None), "codex")

    def test_does_not_route_an_entry_whose_subject_merely_names_claude(self):
        """The old fallback would misroute this: another author, subject naming Claude."""
        entry = ("## 2026-07-28 — Codex — Claude should audit the artifact\n"
                 "- **Seq:** 63\n"
                 + RELEASED + "\n"
                 "- Claude should pick this up next.\n")
        self.assertEqual(DASH.handoff_target(entry, "codex"), "claude")
        self.assertEqual(DASH.handoff_target(entry, None), "claude")

    def test_author_parsing_fails_closed(self):
        for heading in ("## no author field here", "## 2026-07-28", ""):
            entry = heading + "\n- **Seq:** 9\n" + RELEASED + "\n"
            self.assertIsNone(DASH.handoff_target(entry, "codex"), repr(heading))

    def test_status_gate_still_required(self):
        entry = ("## 2026-07-28 — Claude — still working\n"
                 "- **Seq:** 5\n"
                 "- **Status:** implementation ownership\n")
        self.assertIsNone(DASH.handoff_target(entry, "codex"))

    def test_entry_author_extracts_the_author_field_only(self):
        self.assertEqual(
            DASH.entry_author("## 2026-07-28 — Claude — subject naming Codex\n"), "claude")
        self.assertEqual(
            DASH.entry_author("## 2026-07-28 — Codex — subject naming Claude\n"), "codex")


class OpenClaimTests(unittest.TestCase):
    """An ownership claim is binding until its author releases it, and the supervisor must see it.

    Routing is by author, so the moment either agent appends a release the other is handed work.
    The dispatcher only ever read the *latest* entry, so an outstanding claim was invisible to it
    and `send_handoff` read the claimant's "busy" as stale UI work worth a C-c. Seq 182 records
    the supervisor doing this to a Claude pane mid-handoff.
    """

    def entry(self, author, seq, status):
        return f"## 2026-07-29 — {author} — subject\n- **Seq:** {seq}\n- **Status:** {status}\n\n"

    def holders(self, *entries):
        return DASH.open_claim_holders("".join(entries))

    def test_a_claim_without_a_release_is_open(self):
        self.assertEqual(
            self.holders(self.entry("Codex", 1, "claiming; measurement in progress")), {"codex"})

    def test_a_later_release_by_the_same_author_closes_it(self):
        self.assertEqual(
            self.holders(self.entry("Codex", 1, "ownership claim; in progress"),
                         self.entry("Codex", 2, "complete; ownership **RELEASED**")), set())

    def test_only_the_authors_most_recent_entry_counts(self):
        """A release followed by a fresh claim is open again; order, not presence, decides."""
        self.assertEqual(
            self.holders(self.entry("Codex", 1, "complete; ownership **RELEASED**"),
                         self.entry("Codex", 2, "claiming the next measurement")), {"codex"})

    def test_a_claim_describing_its_own_future_release_is_still_open(self):
        """Seq 125's real wording. "until I release" is a promise, not a release."""
        self.assertEqual(
            self.holders(self.entry("Claude 2", 1,
                                    "claiming — do not edit `scripts/b8b_*` until I release")),
            {"claude"})

    def test_both_agents_can_hold_claims_at_once(self):
        self.assertEqual(
            self.holders(self.entry("Codex", 1, "claiming area A"),
                         self.entry("Claude", 2, "claiming area B")), {"codex", "claude"})

    def test_an_author_with_no_entries_holds_nothing(self):
        self.assertEqual(
            self.holders(self.entry("Codex", 1, "complete; ownership **RELEASED**")), set())

    def test_the_real_log_is_parsed_without_error(self):
        """The production log is 5,000 lines of historically irregular formatting."""
        self.assertTrue(DASH.open_claim_holders().issubset(set(DASH.AGENTS)))


class PaneIdentityTests(unittest.TestCase):
    """Pins the defect in `agent_discussion.md` Seq 171.

    `pane_id()` preferred a **stored** map and never revalidated it, and its fallback matched on
    `pane_title` — which the Claude Code TUI overwrites with the agent's current activity. When the
    dashboard restarted and panes were recreated, the stored map bound `codex` to Claude 2's own
    pane, so **every handoff each agent sent the other was typed into its own terminal** for hours.
    Both panes run `claude` and both look alive, so every downstream guard passed.

    Identity now lives in a tmux per-pane user option, which the application cannot overwrite.
    """

    PANES = ["%28", "%29"]

    def setUp(self):
        self.originals = (DASH.tmux, DASH.read_state)
        self.tags = {}
        def fake_tmux(*args, capture=False, check=True):
            if args[0] == "list-panes":
                return "\n".join(self.PANES)
            if args[0] == "show-options":
                return self.tags.get(args[3], "")
            if args[0] == "set-option":
                self.tags[args[3]] = args[5] if len(args) > 5 else ""
                return 0
            return ""
        DASH.tmux = fake_tmux
        self.addCleanup(lambda: setattr(DASH, "tmux", self.originals[0]))
        self.addCleanup(lambda: setattr(DASH, "read_state", self.originals[1]))

    def stored(self, mapping):
        DASH.read_state = lambda: {"panes": mapping}

    def test_the_live_tag_wins_over_a_transposed_stored_map(self):
        """The exact production failure: the stored map said codex was the other agent's pane."""
        self.tags["%28"], self.tags["%29"] = "claude", "codex"
        self.stored({"codex": "%28", "claude": "%29"})      # transposed, as it was on disk
        self.assertEqual(DASH.pane_id("codex"), "%29")
        self.assertEqual(DASH.pane_id("claude"), "%28")

    def test_an_untagged_stored_pane_is_accepted(self):
        """A dashboard predating tagging still works, so the fix is not a flag day."""
        self.stored({"codex": "%28"})
        self.assertEqual(DASH.pane_id("codex"), "%28")

    def test_a_stored_pane_tagged_for_someone_else_is_refused(self):
        self.tags["%28"] = "claude"
        self.stored({"codex": "%28"})
        with self.assertRaises(RuntimeError) as ctx:
            DASH.pane_id("codex")
        self.assertIn("tagged", str(ctx.exception))

    def test_a_stored_pane_that_no_longer_exists_is_refused(self):
        self.stored({"codex": "%99"})
        with self.assertRaises(RuntimeError) as ctx:
            DASH.pane_id("codex")
        self.assertIn("no longer exists", str(ctx.exception))

    def test_no_tag_and_no_stored_entry_refuses_rather_than_guessing(self):
        self.stored({})
        with self.assertRaises(RuntimeError):
            DASH.pane_id("codex")

    def test_tagging_round_trips(self):
        DASH.tag_pane("%28", "claude")
        self.assertEqual(DASH.pane_agent("%28"), "claude")
        self.assertEqual(DASH.tagged_panes(), {"claude": "%28"})

    def test_duplicate_live_identity_tags_are_refused(self):
        self.tags["%28"] = self.tags["%29"] = "codex"
        with self.assertRaises(RuntimeError) as ctx:
            DASH.tagged_panes()
        self.assertIn("duplicate", str(ctx.exception))

    def test_unknown_live_identity_tag_is_refused(self):
        self.tags["%28"] = "claude3"
        with self.assertRaises(RuntimeError) as ctx:
            DASH.tagged_panes()
        self.assertIn("unknown", str(ctx.exception))


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
        self.saved_sleep, DASH.time.sleep = DASH.time.sleep, lambda _s: None

    def tearDown(self):
        DASH.time.sleep = self.saved_sleep
        DASH.tmux, DASH.pane_id, DASH.write_state = self.originals

    def test_send_refuses_a_pane_tagged_for_a_different_agent(self):
        """The last line of defence for the Seq-171 defect.

        `pane_id()` now resolves by tag, but `send()` must assert the recipient too: the old
        post-condition only checked that the composer emptied, which it did — the text went into a
        real terminal, just the wrong agent's. A delivery check that cannot identify the recipient
        is why "the other agent is unresponsive" was diagnosed for hours.
        """
        saved = DASH.pane_agent
        DASH.pane_agent = lambda pane: "claude"
        self.addCleanup(lambda: setattr(DASH, "pane_agent", saved))
        DASH.tmux = self._tmux_with_command("claude")
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("codex", "handoff")
        self.assertIn("tagged", str(ctx.exception))
        self.assertNotIn(("state", ), [(c[0],) for c in self.calls],
                         "a refused send must not record a delivery")

    def test_send_proceeds_when_the_tag_matches(self):
        saved = DASH.pane_agent
        DASH.pane_agent = lambda pane: "codex"
        self.addCleanup(lambda: setattr(DASH, "pane_agent", saved))
        DASH.tmux = self._tmux_with_command("claude")
        DASH.send("codex", "handoff")
        self.assertTrue(any(c[0] == "state" for c in self.calls))

    def _tmux_with_command(self, command, pane_text="❯ "):
        """`pane_text` models what capture-pane returns: the composer line, plus the busy marker
        when the agent is mid-turn. send() now reads it back to verify the message was submitted."""
        def fake(*args, capture=False, check=True):
            if args and args[0] == "display-message":
                return command
            if args and args[0] == "capture-pane":
                return pane_text
            self.calls.append(("tmux", args))
            return 0
        return fake

    def sent_keys(self):
        return [c for c in self.calls if c[0] == "tmux" and c[1][0] == "send-keys"]

    def test_refuses_to_send_into_a_shell_prompt(self):
        for shell in ("zsh", "bash", "sh"):
            self.calls.clear()
            DASH.tmux = self._tmux_with_command(shell)
            with self.assertRaises(RuntimeError) as ctx:
                DASH.send("codex", "handoff")
            self.assertIn("refusing", str(ctx.exception))
            self.assertEqual(self.sent_keys(), [], "must not send keys at all")
            self.assertEqual([c for c in self.calls if c[0] == "state"], [],
                             "must not record a delivery that did not happen")

    def test_refuses_when_the_pane_is_gone(self):
        DASH.tmux = self._tmux_with_command("")
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("codex", "handoff")
        self.assertIn("gone", str(ctx.exception))
        self.assertEqual([c for c in self.calls if c[0] == "state"], [])

    def test_sends_and_records_when_an_agent_is_running(self):
        DASH.tmux = self._tmux_with_command("claude")
        DASH.send("codex", "handoff")
        self.assertEqual(len(self.sent_keys()), 2, "literal text then Enter")
        state = [c for c in self.calls if c[0] == "state"]
        self.assertEqual(len(state), 1)
        self.assertEqual(state[0][1]["last_target"], "codex")
        self.assertEqual(state[0][1]["last_send_pane_command"], "claude")

    def test_refuses_when_the_message_is_left_sitting_in_the_composer(self):
        """The defect that made the owner relay our handoffs by hand for a day.

        `pane_current_command` is `claude` whether the agent is idle or mid-turn, so the Seq-27
        guard could not see this. The keystrokes land in the composer, the Enter is eaten by the
        running turn, and the message sits there as draft text — while state recorded a delivery.
        """
        message = "Read the latest handoff in agent_discussion.md and continue"
        DASH.tmux = self._tmux_with_command("claude", pane_text=f"❯ {message}")
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("codex", message)
        self.assertIn("NOT submitted", str(ctx.exception))
        self.assertEqual([c for c in self.calls if c[0] == "state"], [],
                         "a message still in the composer is not a delivery")

    def test_an_empty_composer_after_sending_counts_as_delivered(self):
        """The other side of the boundary: over-strictness here would break every real handoff."""
        DASH.tmux = self._tmux_with_command("claude", pane_text="❯ ")
        DASH.send("codex", "handoff")
        self.assertEqual(len([c for c in self.calls if c[0] == "state"]), 1)

    def test_a_slowly_accepted_submission_counts_as_delivered_when_turn_starts(self):
        """The live Seq-208 race: text survives one redraw, then Claude starts the turn."""
        message = "Read the latest handoff in agent_discussion.md and continue"
        snapshots = [f"❯ {message}",
                     f"❯ {message}\n⏵⏵ auto mode on · {DASH.BUSY_MARKER}"]

        def fake(*args, capture=False, check=True):
            if args[0] == "display-message":
                return "claude"
            if args[0] == "capture-pane":
                return snapshots.pop(0) if len(snapshots) > 1 else snapshots[0]
            self.calls.append(("tmux", args))
            return 0

        DASH.tmux = fake
        DASH.send("codex", message)
        self.assertEqual(len([c for c in self.calls if c[0] == "state"]), 1)

    def test_preexisting_busy_marker_cannot_prove_the_new_message_was_submitted(self):
        """A level-triggered marker from the old turn is not an acceptance edge for ours."""
        message = "Read the latest handoff in agent_discussion.md and continue"
        saved = DASH.wait_for_idle
        DASH.wait_for_idle = lambda pane: False
        self.addCleanup(lambda: setattr(DASH, "wait_for_idle", saved))
        snapshots = [f"❯ \n⏵⏵ auto mode on · {DASH.BUSY_MARKER}",
                     f"❯ {message}\n⏵⏵ auto mode on · {DASH.BUSY_MARKER}"]

        def fake(*args, capture=False, check=True):
            if args[0] == "display-message":
                return "claude"
            if args[0] == "capture-pane":
                return snapshots.pop(0) if len(snapshots) > 1 else snapshots[0]
            self.calls.append(("tmux", args))
            return 0

        DASH.tmux = fake
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("codex", message)
        self.assertIn("NOT submitted", str(ctx.exception))
        self.assertEqual([c for c in self.calls if c[0] == "state"], [],
                         "pre-existing busy state must not consume the handoff sequence")

    def test_someone_elses_draft_text_is_not_mistaken_for_ours(self):
        """A composer holding unrelated text must not fail the send - it is not our message."""
        DASH.tmux = self._tmux_with_command("claude", pane_text="❯ some unrelated draft")
        DASH.send("codex", "a completely different handoff message")
        self.assertEqual(len([c for c in self.calls if c[0] == "state"]), 1)

    def test_waits_for_the_agent_to_finish_before_typing(self):
        """Busy first, then idle: nothing may be typed until the turn in flight has ended."""
        states = [f"⏵⏵ auto mode on · {DASH.BUSY_MARKER} · ← 1 agent\n❯ "] * 3 + ["❯ "]
        order = []

        def fake(*args, capture=False, check=True):
            if args[0] == "display-message":
                return "claude"
            if args[0] == "capture-pane":
                order.append("poll")
                return states.pop(0) if len(states) > 1 else states[0]
            order.append(args[0])
            self.calls.append(("tmux", args))
            return 0

        DASH.tmux = fake
        DASH.send("codex", "handoff")
        first_send = order.index("send-keys")
        self.assertGreaterEqual(order[:first_send].count("poll"), 3,
                                "must poll until idle before typing")
        self.assertEqual(len([c for c in self.calls if c[0] == "state"]), 1)

    def test_agent_busy_reads_the_status_line_not_a_timer(self):
        """Anchored on the claim, per Seq 160. An elapsed timer in transcript text is not busy."""
        DASH.tmux = self._tmux_with_command("claude", pane_text="ran in (51s) earlier\n❯ ")
        self.assertFalse(DASH.agent_busy("%15"))
        DASH.tmux = self._tmux_with_command(
            "claude", pane_text=f"⏵⏵ auto mode on · {DASH.BUSY_MARKER}\n❯ ")
        self.assertTrue(DASH.agent_busy("%15"))

    def test_handoff_only_interrupts_an_agent_that_is_actually_busy(self):
        """C-c into an idle pane clears a composer the operator may be using."""
        DASH.tmux = self._tmux_with_command("claude", pane_text="❯ ")
        DASH.send_handoff("codex", "handoff")
        interrupts = [c for c in self.sent_keys() if "C-c" in c[1]]
        self.assertEqual(interrupts, [], "an idle agent must not be interrupted")

    def test_rejects_unknown_agent_before_touching_tmux(self):
        DASH.tmux = self._tmux_with_command("claude")
        with self.assertRaises(ValueError):
            DASH.send("claude3", "handoff")
        self.assertEqual(self.calls, [])

    def test_a_delivered_message_echoed_into_the_transcript_is_not_read_as_pending(self):
        """The live defect behind eleven identical "NOT submitted" lines in supervisor.log.

        Claude Code echoes a *delivered* user message back into the transcript behind the same
        `❯` glyph the composer uses. Reading the first match from the top therefore found the
        echo of the message that had just landed, so `send()` raised, the supervisor left the Seq
        unconsumed, and it retried the same delivered handoff forever.
        """
        message = "Read the latest handoff in agent_discussion.md and continue"
        delivered = (f"❯ {message}\n"                     # transcript echo: already delivered
                     "\n  ⎿  the agent's reply\n"
                     "────────────────────────\n"
                     "❯ \n"                               # the live composer, empty
                     "────────────────────────\n"
                     "  ⏵⏵ auto mode on")
        DASH.tmux = self._tmux_with_command("claude", pane_text=delivered)
        self.assertEqual(DASH.composer_text("%9"), "")
        DASH.send("codex", message)                       # must not raise
        self.assertEqual(len([c for c in self.calls if c[0] == "state"]), 1,
                         "a delivered handoff must be recorded, not retried forever")

    def test_a_draft_below_an_old_echo_is_still_seen(self):
        """The boundary: scanning from the bottom must not blind the check to a real draft."""
        message = "Read the latest handoff in agent_discussion.md and continue"
        DASH.tmux = self._tmux_with_command(
            "claude", pane_text=f"❯ an older message\n────\n❯ {message}\n────")
        self.assertEqual(DASH.composer_text("%9"), message)
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("codex", message)
        self.assertIn("NOT submitted", str(ctx.exception))

    def test_the_codex_composer_prompt_is_recognised(self):
        """Codex draws `›` (U+203A), not Claude Code's `❯` (U+276F).

        Matching only Claude's glyph made the post-condition *inert* for the Codex pane rather
        than wrong: `composer_text()` returned "" for every capture, so an undelivered handoff was
        recorded as delivered. A check that cannot fail is worse than one that fails loudly.
        """
        message = "Read the latest handoff in agent_discussion.md and continue"
        DASH.tmux = self._tmux_with_command("codex", pane_text=f"› {message}\n────")
        self.assertEqual(DASH.composer_text("%9"), message)
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("claude", message)
        self.assertIn("NOT submitted", str(ctx.exception))
        self.assertEqual([c for c in self.calls if c[0] == "state"], [],
                         "an undelivered handoff into Codex must not be recorded as delivered")

    def _busy_pane(self):
        """A pane that reports busy forever, with the idle wait stubbed so tests stay fast."""
        DASH.tmux = self._tmux_with_command(
            "claude", pane_text=f"⏵⏵ auto mode on · {DASH.BUSY_MARKER}\n❯ ")
        saved, DASH.wait_for_idle = DASH.wait_for_idle, lambda pane, **kw: False
        self.addCleanup(lambda: setattr(DASH, "wait_for_idle", saved))

    def test_a_handoff_is_not_forced_into_an_agent_holding_an_open_claim(self):
        """C-c into a busy pane cannot tell stale UI work from claimed work in flight."""
        self._busy_pane()
        try:
            DASH.send_handoff("codex", "handoff", interrupt_busy=False)
        except RuntimeError:
            pass                                   # delivery may still refuse; not what is asserted
        self.assertEqual([c for c in self.sent_keys() if "C-c" in c[1]], [],
                         "an agent holding an open claim must never be interrupted")

    def test_a_busy_agent_without_a_claim_is_still_interrupted(self):
        """The boundary: the protection must be the claim, not merely being busy."""
        self._busy_pane()
        try:
            DASH.send_handoff("codex", "handoff")
        except RuntimeError:
            pass
        self.assertTrue([c for c in self.sent_keys() if "C-c" in c[1]],
                        "stale UI work is still cleared before a handoff")


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


class SupervisorModeTests(IsolatedDashboard):
    """`stop` must not disable automatic handoffs (Seq 165).

    `STOP` is a lifecycle signal and `mode` is a policy. Conflating them meant restarting the
    supervisor silently killed dispatch: `status: running`, forwarding nothing, and no message
    anywhere saying so. Walked into it in production while restarting for the delivery fix.
    """

    dash = DASH

    def test_stop_leaves_the_dispatch_policy_alone(self):
        DASH.write_state(mode="auto", owner="supervisor")
        DASH.STOP.touch()                       # what the `stop` command now does
        self.assertEqual(DASH.read_state()["mode"], "auto",
                         "stopping the process must not change whether handoffs are automatic")

    def test_pause_is_what_disables_handoffs(self):
        DASH.write_state(mode="auto", owner="supervisor")
        DASH.write_state(mode="manual", owner="none")     # what `pause` does
        self.assertEqual(DASH.read_state()["mode"], "manual")

    def test_the_real_stop_command_preserves_auto_mode(self):
        """Runs the actual CLI handler, not a copy of it or a scrape of its source.

        This is the regression that matters: `stop` used to call
        `write_state(mode="manual", ...)`, so restarting the supervisor left dispatch silently
        disabled. A source-text assertion would pass on a handler that had been refactored into
        a helper; invoking the command cannot.
        """
        import contextlib
        import io
        import sys
        DASH.write_state(mode="auto", owner="supervisor")
        saved_argv = sys.argv
        sys.argv = ["interactive_dashboard.py", "stop"]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                DASH.main()
        finally:
            sys.argv = saved_argv
        self.assertTrue(DASH.STOP.exists(), "stop must still signal the process to exit")
        self.assertEqual(DASH.read_state()["mode"], "auto",
                         "stopping the process must not disable automatic handoffs")

    def run_loop_once(self):
        """Run `supervisor_loop` for exactly one startup pass.

        The loop calls `STOP.unlink(missing_ok=True)` on entry, so a pre-created STOP file cannot
        end it — it spins forever, which is exactly what my first version of this test did.
        Substituting the sentinel is the only way to observe startup behaviour while still running
        the real loop, and running the real loop is the point: asserting against a copy of the
        warning string would pin nothing.
        """
        import contextlib
        import io

        class Sentinel:
            def unlink(self, missing_ok=False):
                pass

            def exists(self):
                return True                     # stop before the first iteration

            def touch(self):
                pass

        saved, DASH.STOP = DASH.STOP, Sentinel()
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                DASH.supervisor_loop(interval=0.01)
        finally:
            DASH.STOP = saved
        return captured.getvalue()

    def seed(self, mode, owner):
        DASH.write_state(mode=mode, owner=owner, observed_sequence=1)
        DASH.DISCUSSION.write_text("## d — Claude — x\n- **Seq:** 1\n- **Status:** handoff\n",
                                   encoding="utf-8")

    def test_supervisor_warns_when_it_would_dispatch_nothing(self):
        """A dispatcher forwarding nothing must say so, not merely report `status: running`."""
        self.seed("manual", "none")
        self.assertIn("automatic handoffs DISABLED", self.run_loop_once())

    def test_no_warning_when_dispatch_is_live(self):
        """The other side of the boundary: a healthy supervisor must not cry wolf."""
        self.seed("auto", "supervisor")
        self.assertNotIn("DISABLED", self.run_loop_once())


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


class SupervisorResilienceTests(IsolatedDashboard):
    """An undeliverable handoff must not kill the dispatcher, and must not be recorded as sent.

    `supervisor_loop` called `send_handoff` unguarded, so the first `RuntimeError` the delivery
    check raised propagated out of the loop and **ended the supervisor process**. That is the
    mechanism behind supervisors repeatedly found dead with `status: running` in the state file:
    a busy agent — an ordinary, transient condition — permanently stopped dispatch.

    The sequence must also stay unconsumed, or the retry never happens: consuming it would mark
    the handoff observed while nothing was delivered, which is the same "recorded a delivery that
    did not happen" failure the delivery check exists to prevent, one level up.
    """

    dash = DASH

    def setUp(self):
        super().setUp()
        DASH.write_state(mode="auto", owner="supervisor", active_agent="claude",
                         observed_sequence=1)
        DASH.DISCUSSION.write_text(
            "## d — Claude — released\n- **Seq:** 2\n- **Status:** released\n", encoding="utf-8")

    def run_one_iteration(self, handoff):
        """Run `supervisor_loop` for exactly one dispatching pass.

        The existing `run_loop_once` helper stops *before* the first iteration, which is right for
        startup warnings and useless here. This sentinel reports "keep going" once and then stops,
        so the loop performs one real dispatch attempt against the real code path.
        """
        import contextlib
        import io

        class Sentinel:
            def __init__(self):
                self.checks = 0

            def unlink(self, missing_ok=False):
                pass

            def exists(self):
                self.checks += 1
                return self.checks > 1          # one iteration, then stop

            def touch(self):
                pass

        saved_stop, DASH.STOP = DASH.STOP, Sentinel()
        saved_handoff, DASH.send_handoff = DASH.send_handoff, handoff
        self.tmux_calls = []
        saved_tmux, DASH.tmux = DASH.tmux, lambda *a, **k: self.tmux_calls.append(a) or 0
        saved_pane, DASH.pane_id = DASH.pane_id, lambda agent: "%9"
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                DASH.supervisor_loop(interval=0.001)
        finally:
            (DASH.STOP, DASH.send_handoff, DASH.tmux,
             DASH.pane_id) = saved_stop, saved_handoff, saved_tmux, saved_pane
        return captured.getvalue()

    def test_an_undeliverable_handoff_does_not_kill_the_supervisor(self):
        def refuse(agent, message, interrupt_busy=True):
            raise RuntimeError("agent is mid-turn")

        output = self.run_one_iteration(refuse)          # must not propagate
        self.assertIn("handoff pending", output,
                      "an undeliverable handoff must be reported, not swallowed silently")

    def test_an_undeliverable_handoff_leaves_the_sequence_unconsumed_so_it_retries(self):
        def refuse(agent, message, interrupt_busy=True):
            raise RuntimeError("agent is mid-turn")

        self.run_one_iteration(refuse)
        self.assertEqual(DASH.read_state()["observed_sequence"], 1,
                         "consuming the sequence would record a handoff that was never delivered")

    def test_a_delivered_handoff_consumes_the_sequence_and_moves_ownership(self):
        """The other side of the boundary: a working dispatch must still advance."""
        delivered = []
        self.run_one_iteration(
            lambda agent, message, interrupt_busy=True: delivered.append(agent))
        self.assertEqual(delivered, ["codex"])
        state = DASH.read_state()
        self.assertEqual(state["observed_sequence"], 2)
        self.assertEqual(state["active_agent"], "codex")

    def dispatch_with_codex_status(self, status):
        """One dispatch pass whose target, Codex, last wrote an entry with `status`."""
        DASH.DISCUSSION.write_text(
            f"## d — Codex — earlier\n- **Seq:** 1\n- **Status:** {status}\n\n"
            "## d — Claude — released\n- **Seq:** 2\n- **Status:** released\n", encoding="utf-8")
        DASH.write_state(observed_sequence=1)
        seen = {}
        self.run_one_iteration(
            lambda agent, message, interrupt_busy=True: seen.update(interrupt=interrupt_busy))
        return seen["interrupt"]

    def test_the_dispatcher_does_not_interrupt_a_target_holding_an_open_claim(self):
        """The live case: Codex mid-run on a claimed B9b measurement when Claude released."""
        self.assertIs(self.dispatch_with_codex_status("claiming; in progress"), False)

    def test_the_dispatcher_still_interrupts_a_target_with_no_open_claim(self):
        self.assertIs(self.dispatch_with_codex_status("complete; ownership released"), True)

    def test_a_source_holding_an_open_claim_is_not_interrupted_either(self):
        """`active_agent` is interrupted when work moves on. A claim protects it there too."""
        DASH.DISCUSSION.write_text(
            "## d — Claude — claiming\n- **Seq:** 1\n- **Status:** claiming area A\n\n"
            "## d — Codex — released\n- **Seq:** 2\n- **Status:** released\n", encoding="utf-8")
        DASH.write_state(active_agent="claude", observed_sequence=1)
        self.run_one_iteration(lambda agent, message, interrupt_busy=True: None)
        self.assertEqual([c for c in self.tmux_calls if "C-c" in c], [],
                         "the outgoing agent's claimed work must survive the handoff too")


class PendingComposerTests(IsolatedDashboard):
    """A retry must submit the draft already in the composer, never append a second copy.

    Once `send()` began refusing undelivered handoffs, the natural retry typed the whole message
    again into a composer that already held it — producing a doubled handoff that reads as
    corruption. Matching on a prefix of what is already there distinguishes *our* pending draft
    from text the owner happens to be typing.
    """

    dash = DASH

    def arrange(self, pending, idle):
        self.sent = []
        self.saved = (DASH.tmux, DASH.pane_id, DASH.pane_command,
                      DASH.wait_for_idle, DASH.composer_text, DASH.pane_text)
        DASH.tmux = lambda *a, **k: self.sent.append(a) or 0
        DASH.pane_id = lambda agent: "%9"
        DASH.pane_command = lambda pane: "claude"
        DASH.wait_for_idle = lambda pane: idle
        DASH.composer_text = lambda pane: pending
        DASH.pane_text = lambda pane: f"❯ {pending}"
        self.addCleanup(self.restore)

    def restore(self):
        (DASH.tmux, DASH.pane_id, DASH.pane_command,
         DASH.wait_for_idle, DASH.composer_text, DASH.pane_text) = self.saved

    def test_a_pending_draft_of_ours_is_submitted_not_retyped(self):
        message = "Read the latest handoff in agent_discussion.md and continue the work."
        self.arrange(pending=message[:40], idle=True)
        with self.assertRaises(RuntimeError):
            DASH.send("codex", message)        # post-condition still sees it pending
        typed = [a for a in self.sent if len(a) > 3 and a[3] == "-l"]
        self.assertEqual(typed, [], "the message must not be typed again on top of itself")
        self.assertTrue(any(a[-1] == "Enter" for a in self.sent), "the draft must be submitted")

    def test_a_pending_draft_with_a_busy_agent_refuses_rather_than_pressing_enter(self):
        message = "Read the latest handoff in agent_discussion.md and continue the work."
        self.arrange(pending=message[:40], idle=False)
        with self.assertRaises(RuntimeError) as ctx:
            DASH.send("codex", message)
        self.assertIn("pending", str(ctx.exception))
        self.assertEqual([a for a in self.sent if a[-1] == "Enter"], [],
                         "pressing Enter into a busy agent is what created the draft to begin with")

    def test_someone_elses_draft_is_not_mistaken_for_ours(self):
        """The boundary that keeps this safe: unrelated composer text must not suppress the send."""
        self.arrange(pending="a note the owner was typing", idle=True)
        try:
            DASH.send("codex", "Read the latest handoff in agent_discussion.md and continue.")
        except RuntimeError:
            pass                                  # post-condition may still fire; not the point
        typed = [a for a in self.sent if len(a) > 3 and a[3] == "-l"]
        self.assertEqual(len(typed), 1, "our message must still be typed when the draft is not ours")


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
        self.launched = {}

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
                return self.launched[pane]
            return "zsh"
        if args[0] == "capture-pane":
            pane = args[3]
            if self.shell_polls[pane] > 0:
                self.shell_polls[pane] -= 1
                return ""                               # prompt not drawn yet
            return "user@host %"
        if args[0] == "split-window":
            return f"%{len(self.calls)}"
        if args[0] == "send-keys" and args[3] == "-l":
            for agent, marker in zip(DASH.AGENTS, LAUNCH_MARKERS):
                if marker in args[4]:
                    self.launched[args[2]] = agent
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
        fake.launched["%1"] = "claude"
        self.assertEqual(DASH.wait_for_app("%1"), "claude")

    def test_wait_for_app_times_out_while_a_shell_persists(self):
        fake = FakeTmux(shell_polls=0, app_polls=10 ** 6)
        DASH.tmux = fake
        fake.launched["%1"] = "claude"
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
            launch = next((self._index_of_send(pane, marker) for marker in LAUNCH_MARKERS
                           if self._index_of_send(pane, marker) is not None), None)
            identity = self._index_of_send(pane, "You are ")
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
        DASH.start("codex")
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
                return ("%1\tcodex\tcodex\n"
                        "%2\tclaude\tzsh\n"          # not running an agent: triggers respawn
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
        return any(a[0] == "send-keys" and len(a) > 4
                   and any(marker in a[4] for marker in LAUNCH_MARKERS)
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


class UpgradeExistingIdentityTests(IsolatedDashboard):
    """An upgrade must never manufacture authoritative identities from pane order."""

    dash = DASH

    def setUp(self):
        super().setUp()
        self.saved_tmux, self.saved_sleep = DASH.tmux, DASH.time.sleep
        DASH.time.sleep = lambda _s: None
        self.calls = []
        self.tags = {}

    def tearDown(self):
        DASH.tmux, DASH.time.sleep = self.saved_tmux, self.saved_sleep
        super().tearDown()

    def install(self, rows):
        def fake(*args, capture=False, check=True):
            self.calls.append(args)
            if args[0] == "has-session":
                return 0
            if args[0] == "list-panes":
                return rows
            if args[0] == "show-options":
                return self.tags.get(args[3], "")
            if args[0] == "set-option":
                self.tags[args[3]] = args[5]
                return 0
            return 0
        DASH.tmux = fake

    def test_two_anonymous_claude_panes_are_not_assigned_by_sorted_id(self):
        self.install("%8\tRead markdown\tclaude\n%3\tResearching\tclaude\n"
                     "%9\tcontrol\tzsh")
        with self.assertRaises(RuntimeError) as ctx:
            DASH.upgrade_existing()
        self.assertIn("without guessing", str(ctx.exception))
        self.assertFalse(any(call[0] == "set-option" for call in self.calls),
                         "ambiguity must fail before a guessed identity is made authoritative")

    def test_unique_live_tags_override_misleading_cosmetic_titles(self):
        self.tags = {"%8": "codex", "%3": "claude", "%9": "control"}
        self.install("%8\tResearching B9\tcodex\n%3\tRead all markdown\tclaude\n"
                     "%9\tanything\tzsh")
        DASH.upgrade_existing()
        self.assertEqual(self.tags,
                         {"%8": "codex", "%3": "claude", "%9": "control"})

    def test_conflicting_tag_and_legacy_title_is_refused(self):
        self.tags = {"%8": "claude"}
        self.install("%8\tcodex\tclaude\n%3\tclaude\tclaude\n%9\tcontrol\tzsh")
        with self.assertRaises(RuntimeError) as ctx:
            DASH.upgrade_existing()
        self.assertIn("conflicting", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
