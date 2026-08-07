"""B20b guards — the operator control surface.

Two properties carry the weight here, and both are about what this file must NOT do:

- `test_no_subcommand_accepts_the_secret` — argv is visible in `ps` to every user on the machine,
  lands in shell history and is captured by process accounting. The whole reason the CLI lives in a
  separate file from `b20a` is to keep the secret out of it, and that is worth asserting rather
  than remembering.
- `test_this_surface_holds_no_policy_of_its_own` — every rule belongs to `b20a`. A control surface
  carrying its own copy of the rules is a second implementation of the thing it controls, and the
  two eventually disagree. The test neuters `b20a` and shows the CLI stops being able to decide
  anything, which is the only way to show the policy is not secretly duplicated here.

No network, no wallet, no key, no transaction.
"""
import importlib.util
import io
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B20B = load("b20b_emergency_control", "b20b_emergency_control.py")
B20A = B20B.B20A

SECRET_VALUE = "an-operator-secret-not-a-wallet-key"
NOW = 1_786_000_000_000_000_000
SECOND = 1_000_000_000


class Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="b20b-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.state = self.dir / "emergency_state.json"
        self.receipts = self.dir / "receipts.jsonl"
        import os
        os.environ[B20A.OPERATOR_SECRET_ENV] = SECRET_VALUE
        self.addCleanup(os.environ.pop, B20A.OPERATOR_SECRET_ENV, None)

    def run_cli(self, *argv, now=NOW):
        out = io.StringIO()
        code = B20B.main(["--state", str(self.state), "--receipts", str(self.receipts), *argv],
                         out=out, now=now)
        return code, out.getvalue()


class ExitCodeTests(Fixture):
    """A supervisor should branch on the state without parsing prose."""

    def test_no_state_reports_engaged(self):
        code, text = self.run_cli("status")
        self.assertEqual(code, B20B.EXIT_ENGAGED)
        self.assertIn("ENGAGED", text)

    def test_status_is_the_default_subcommand(self):
        code, text = self.run_cli()
        self.assertEqual(code, B20B.EXIT_ENGAGED)
        self.assertIn("emergency state", text)

    def test_a_cleared_switch_reports_clear(self):
        self.run_cli("engage", "--reason", "a fault", "--operator", "op")
        code, _ = self.run_cli("clear", "--reason", "reviewed", "--operator", "op",
                               "--expect-generation", "1")
        self.assertEqual(code, B20B.EXIT_CLEAR)

    def test_engaging_exits_engaged(self):
        """A supervisor branching on the exit code must not read a halt as success."""
        code, _ = self.run_cli("engage", "--reason", "a fault", "--operator", "op")
        self.assertEqual(code, B20B.EXIT_ENGAGED)

    def test_clearing_requires_the_expected_generation_to_be_supplied(self):
        """Without it, an operator clears a halt they never looked at."""
        self.run_cli("engage", "--reason", "a fault", "--operator", "op")
        with self.assertRaises(SystemExit) as exited:
            self.run_cli("clear", "--reason", "reviewed", "--operator", "op")
        self.assertNotEqual(exited.exception.code, 0)

    def test_a_refusal_is_its_own_exit_code(self):
        self.run_cli("engage", "--reason", "one", "--operator", "op")
        self.run_cli("engage", "--reason", "two", "--operator", "op")
        code, text = self.run_cli("clear", "--reason", "stale", "--operator", "op",
                                  "--expect-generation", "1")
        self.assertEqual(code, B20B.EXIT_REFUSED)
        self.assertIn("REFUSED", text)


class SecretNeverInArgvTests(Fixture):
    def test_no_subcommand_accepts_the_secret(self):
        """argv is world-readable in `ps`. This is why the CLI is not inside b20a."""
        parser = B20B.build_parser()
        actions = list(parser._actions)
        for action in parser._subparsers._group_actions:
            for sub in action.choices.values():
                actions.extend(sub._actions)
        for action in actions:
            for option in action.option_strings:
                with self.subTest(option=option):
                    self.assertNotIn("secret", option.lower())
                    self.assertNotIn("password", option.lower())
                    self.assertNotIn("token", option.lower())

    def test_the_secret_never_reaches_stdout(self):
        self.run_cli("engage", "--reason", "a fault", "--operator", "op")
        for argv in (("status",), ("status", "--json")):
            with self.subTest(argv=argv):
                _code, text = self.run_cli(*argv)
                self.assertNotIn(SECRET_VALUE, text)

    def test_the_help_text_says_where_the_secret_comes_from(self):
        self.assertIn(B20A.OPERATOR_SECRET_ENV, B20B.build_parser().description)


class NoPolicyOfItsOwnTests(Fixture):
    def test_this_surface_holds_no_policy_of_its_own(self):
        """Neuter the owner and the CLI must lose its ability to decide anything.

        If the surface carried its own copy of the rules it would keep answering, and the two
        implementations would eventually disagree about whether the system is halted.
        """
        self.run_cli("engage", "--reason", "a fault", "--operator", "op")
        real = B20A.read_verdict
        B20A.read_verdict = lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked the owner"))
        self.addCleanup(setattr, B20A, "read_verdict", real)
        with self.assertRaisesRegex(AssertionError, "asked the owner"):
            self.run_cli("status")

    def test_the_module_defines_no_reason_codes_of_its_own(self):
        source = (ROOT / "scripts" / "b20b_emergency_control.py").read_text()
        self.assertNotIn("E09_EXPLICITLY_ENGAGED =", source)
        self.assertNotIn("def read_verdict", source)
        self.assertNotIn("hmac", source, "MACing belongs to the owner, not the surface")


class ClearRechecksTests(Fixture):
    def test_a_clear_that_still_reads_engaged_says_so_and_exits_engaged(self):
        """The worst available failure is an operator walking away believing a halt ended."""
        self.run_cli("engage", "--reason", "a fault", "--operator", "op")
        real = B20A.read_verdict
        B20A.read_verdict = lambda *a, **k: B20A._verdict(
            True, B20A.E08_VERIFIER_DISAGREEMENT, generation=2, detail="receipts disagree")
        self.addCleanup(setattr, B20A, "read_verdict", real)

        code, text = self.run_cli("clear", "--reason", "reviewed", "--operator", "op",
                                  "--expect-generation", "1")

        self.assertEqual(code, B20B.EXIT_ENGAGED)
        self.assertIn("BUT IT READS AS ENGAGED", text)


class FailClosedDefaultIsExplainedTests(Fixture):
    def test_a_default_engagement_is_distinguished_from_an_operator_one(self):
        """An operator who cannot tell "somebody halted this" from "something was unverifiable"
        will eventually treat both as noise."""
        _code, text = self.run_cli("status")
        self.assertIn("FAIL-CLOSED DEFAULT", text)

        self.run_cli("engage", "--reason", "deliberate", "--operator", "op")
        _code, text = self.run_cli("status")
        self.assertNotIn("FAIL-CLOSED DEFAULT", text)


class HeartbeatTests(Fixture):
    def test_a_heartbeat_loop_can_never_clear(self):
        self.run_cli("engage", "--reason", "halt", "--operator", "op")
        beats = []

        class Args:
            state, receipts = self.state, self.receipts
            loop, interval_seconds, max_beats = True, 0, 5

        B20B.do_heartbeat(Args(), io.StringIO(), NOW,
                          clock=lambda: NOW / 1e9, sleeper=beats.append)

        code, _ = self.run_cli("status", now=NOW + SECOND)
        self.assertEqual(code, B20B.EXIT_ENGAGED)

    def test_the_loop_is_bounded_when_asked(self):
        self.run_cli("engage", "--reason", "halt", "--operator", "op")
        out = io.StringIO()

        class Args:
            state, receipts = self.state, self.receipts
            loop, interval_seconds, max_beats = True, 0, 3

        B20B.do_heartbeat(Args(), out, NOW, clock=lambda: NOW / 1e9, sleeper=lambda _s: None)
        self.assertEqual(out.getvalue().count("heartbeat"), 3)

    def test_the_loop_does_not_sleep_after_its_final_beat(self):
        """The whole reason the inner break exists, and a no-op sleeper cannot see it.

        Without it the loop writes its last heartbeat, sleeps the full interval, and only then
        re-checks the bound — so a bounded run takes one extra interval to exit and a supervisor
        waiting on it is left hanging for no reason. A mutation sweep found this: neutering the
        break changed nothing observable while `sleeper` was ignored.
        """
        self.run_cli("engage", "--reason", "halt", "--operator", "op")
        slept = []

        class Args:
            state, receipts = self.state, self.receipts
            loop, interval_seconds, max_beats = True, 15, 3

        B20B.do_heartbeat(Args(), io.StringIO(), NOW, clock=lambda: NOW / 1e9,
                          sleeper=slept.append)

        self.assertEqual(slept, [15, 15],
                         "expected a sleep BETWEEN beats only: 3 beats means 2 gaps, not 3")


class ClockTests(unittest.TestCase):
    def test_the_clock_helper_returns_nanoseconds(self):
        """b20a compares this against nanosecond stamps and a stale-heartbeat window in nanoseconds.

        A seconds-scale value would read as ~1970 against any real record, so every clock check
        would engage on a clock conflict — safe, but permanently and for a fabricated reason.
        """
        self.assertEqual(B20B.now_nanos(clock=lambda: 1_786_000_000.0), 1_786_000_000_000_000_000)

    def test_it_is_an_exact_integer(self):
        value = B20B.now_nanos(clock=lambda: 1_786_000_000.123456)
        self.assertIsInstance(value, int)
        self.assertNotIsInstance(value, float)


class JsonOutputTests(Fixture):
    def test_json_status_is_the_owner_s_snapshot_verbatim(self):
        self.run_cli("engage", "--reason", "a fault", "--operator", "op")
        _code, text = self.run_cli("status", "--json")
        parsed = json.loads(text)
        expected = B20A.snapshot(B20A.read_verdict(NOW, state_path=self.state,
                                                   receipt_path=self.receipts))
        self.assertEqual(parsed, expected)
        self.assertIs(parsed["console_may_mutate_this"], False)


class ReceiptTests(Fixture):
    def test_operator_actions_leave_receipts_with_reasons(self):
        self.run_cli("engage", "--reason", "the watcher died", "--operator", "anont")
        self.run_cli("clear", "--reason", "cause understood", "--operator", "anont",
                     "--expect-generation", "1")
        lines = [json.loads(line) for line in self.receipts.read_text().splitlines() if line.strip()]
        self.assertEqual([r["action"] for r in lines], ["engage", "clear"])
        self.assertEqual([r["reason"] for r in lines],
                         ["the watcher died", "cause understood"])


if __name__ == "__main__":
    unittest.main()
