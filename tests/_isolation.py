"""Shared test isolation for anything that touches production paths.

Why this exists, concretely rather than as hygiene:

`scripts/interactive_dashboard.py` holds module-level paths — `DISCUSSION`, `STATE`, `RUNTIME`,
`SEQ_LOCK`, `SEQ_COUNTER`, `LOG`, `STOP` — that point at **real files**. A test calling
`DASH.DISCUSSION.write_text(...)` without patching `DISCUSSION` overwrites `agent_discussion.md`.
That near-miss happened (`agent_discussion.md` Seq 96) and was caught only by inspection.

The consequence is not recoverable. `/home/anont/.gitignore` line 2 is `/*`, so the entire `meme/`
tree is ignored and **git tracks zero files under it**. There is no version-control safety net
beneath the coordination log, the decision record, or the research artifacts.

So isolation here is not per-class discipline that each author must remember. Two layers:

1. `IsolatedDashboard` — a base class that redirects **every** production path to a temp
   directory, so forgetting to patch one specific attribute cannot reach a real file.
2. `assert_production_untouched()` — a digest guard over the irreplaceable files, so any test that
   writes to one fails loudly instead of succeeding quietly.
"""
import hashlib
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Files with no version-control backup. Losing any of them loses project history outright.
PROTECTED = (
    ROOT / "agent_discussion.md",
    ROOT / "DECISIONS.md",
    ROOT / "PLAN.md",
    ROOT / "DOCUMENTATION.md",
    ROOT / "AGENTS.md",
    ROOT / "docs" / "DEFINITIONS.md",
)

# Every module-level path the dashboard can write through. Listed exhaustively on purpose:
# patching only the attribute a given test happens to use is what produced the near-miss.
DASHBOARD_PATHS = (
    "RUNTIME", "STATE", "LOG", "STOP", "DISCUSSION", "SEQ_LOCK", "SEQ_COUNTER",
    "QUEUE_DB", "SUPERVISOR_LOCK", "HANDOFF_LOCK",
    # Not files, but the same class of leak: these address the LIVE tmux panes. A supervisor that
    # keeps them pointed at production will `send_line` into the real Codex and Claude terminals —
    # which happened, delivering a duplicate protocol announcement into a working agent's pane.
    "SESSION", "TMUX_SOCKET",
)


def digests():
    """Digest of every protected file that currently exists."""
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in PROTECTED if p.exists()}


def assert_production_untouched(before, testcase=None):
    """Fail if any protected file changed. Reports which one, not merely that something did."""
    after = digests()

    def label(path):
        # Never let the reporter itself raise. A guard that crashes while describing a violation
        # turns a clear failure into a confusing traceback at the worst possible moment.
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    changed = sorted(label(p) for p in set(before) | set(after)
                     if before.get(p) != after.get(p))
    if changed:
        message = (f"tests modified untracked production files: {changed}. "
                   f"These have no git backup; a fixture must never write to them.")
        if testcase is not None:
            testcase.fail(message)
        raise AssertionError(message)


class IsolatedDashboard(unittest.TestCase):
    """Base class redirecting every dashboard production path into a temp directory.

    Subclass instead of patching by hand. `self.tmp` is the sandbox; `self.dash` is the module.
    A digest guard runs in `tearDown`, so a test that reaches a real file fails in the test that
    did it rather than somewhere downstream.
    """

    dash = None          # subclass sets this to the imported dashboard module

    def setUp(self):
        if self.dash is None:
            self.skipTest("subclass must set `dash` to the dashboard module")
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self._saved = {name: getattr(self.dash, name) for name in DASHBOARD_PATHS
                       if hasattr(self.dash, name)}
        self.dash.RUNTIME = self.tmp
        self.dash.STATE = self.tmp / "state.json"
        self.dash.LOG = self.tmp / "supervisor.log"
        self.dash.STOP = self.tmp / "STOP"
        self.dash.DISCUSSION = self.tmp / "agent_discussion.md"
        self.dash.SEQ_LOCK = self.tmp / "seq.lock"
        self.dash.SEQ_COUNTER = self.tmp / "seq.counter"
        self.dash.QUEUE_DB = self.tmp / "handoffs.sqlite"
        self.dash.SUPERVISOR_LOCK = self.tmp / "supervisor.lock"
        self.dash.HANDOFF_LOCK = self.tmp / "handoff.lock"
        self.dash.SESSION = f"test-{self.tmp.name}"
        self.dash.TMUX_SOCKET = f"test-socket-{self.tmp.name}"
        self.dash.DISCUSSION.write_text("", encoding="utf-8")
        self._before = digests()

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(self.dash, name, value)
        assert_production_untouched(self._before, self)

    def write_log(self, text):
        """Write fixture content to the *sandboxed* discussion file."""
        self.dash.DISCUSSION.write_text(text, encoding="utf-8")
