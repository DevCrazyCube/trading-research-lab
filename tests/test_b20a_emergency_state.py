"""B20a guards — the emergency-state owner (slice E, closing G6).

Every fail-closed branch is PROVOKED here, not reasoned about. This module's whole value is that
uncertainty engages, and a fail-closed default that no test can reach is indistinguishable from a
permissive one that nobody noticed.

The two that matter most, because they are the ones a careless implementation gets wrong:

- `test_a_restart_does_not_clear_and_neither_does_time` — B19a says the switch never auto-clears.
  The failure mode is not a crash; it is a switch that quietly comes back on its own.
- `test_a_heartbeat_can_never_clear_an_engaged_switch` — a liveness refresh that could flip the flag
  would be an unauthenticated clear wearing a different name.

Nothing here creates a wallet, key, address or transaction, and one test proves that by running
B17a's execution-surface scanner over this module rather than asserting it in prose.
"""
import importlib.util
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


B20A = load("b20a_emergency_state", "b20a_emergency_state.py")
B12A = load("b12a_risk_governor", "b12a_risk_governor.py")
B17A = load("b17a_shadow_rehearsal", "b17a_shadow_rehearsal.py")

SECRET = {B20A.OPERATOR_SECRET_ENV: "an-operator-secret-not-a-wallet-key"}
NOW = 1_786_000_000_000_000_000
SECOND = 1_000_000_000


class Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="b20a-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.state = self.dir / "emergency_state.json"
        self.receipts = self.dir / "receipts.jsonl"

    def read(self, now=NOW, env=SECRET, **kwargs):
        return B20A.read_verdict(now, state_path=self.state, receipt_path=self.receipts,
                                 env=env, **kwargs)

    def engage(self, reason="a fault", operator="op", now=NOW, env=SECRET):
        return B20A.engage(reason, operator, now, state_path=self.state,
                           receipt_path=self.receipts, env=env)

    def clear(self, reason="reviewed", operator="op", expected=None, now=NOW, env=SECRET):
        if expected is None:
            expected = B20A._current_generation(self.state)
        return B20A.clear(reason, operator, expected, now, state_path=self.state,
                          receipt_path=self.receipts, env=env)


class FailClosedReadTests(Fixture):
    """Every branch of the read path, each provoked, each engaging."""

    def test_no_state_at_all_is_engaged(self):
        verdict = self.read()
        self.assertTrue(verdict["kill_switch_engaged"])
        self.assertEqual(verdict["reason_code"], B20A.E01_NO_STATE)

    def test_unreadable_state_is_engaged(self):
        self.state.write_text("{ not json")
        self.assertEqual(self.read()["reason_code"], B20A.E02_UNREADABLE)

    def test_a_tampered_record_is_engaged(self):
        self.engage()
        record = json.loads(self.state.read_text())
        record["engaged"] = False
        self.state.write_text(json.dumps(record))
        self.assertEqual(self.read()["reason_code"], B20A.E03_BAD_MAC)

    def test_a_missing_secret_is_engaged_rather_than_trusted(self):
        self.engage()
        self.assertEqual(self.read(env={})["reason_code"], B20A.E04_NO_SECRET)

    def test_a_stale_heartbeat_is_engaged(self):
        self.engage()
        self.clear(expected=1)
        self.assertFalse(self.read(now=NOW + SECOND)["kill_switch_engaged"])
        late = self.read(now=NOW + 61 * SECOND)
        self.assertTrue(late["kill_switch_engaged"])
        self.assertEqual(late["reason_code"], B20A.E05_STALE_HEARTBEAT)

    def write_valid(self, **overrides):
        """A record with a genuinely valid MAC, so a test can isolate ONE field's guard."""
        record = {"schema_version": B20A.SCHEMA_VERSION, "generation": 1, "engaged": False,
                  "reason": "crafted", "operator": "op", "recorded_unix_nanos": NOW,
                  "heartbeat_unix_nanos": NOW}
        record.update(overrides)
        record["mac"] = B20A.compute_mac(record, B20A._secret(SECRET))
        self.state.write_text(json.dumps(record))
        return record

    def test_a_record_stamped_in_the_future_is_a_clock_conflict(self):
        self.engage()
        self.clear(expected=1)
        conflicted = self.read(now=NOW - SECOND)
        self.assertTrue(conflicted["kill_switch_engaged"])
        self.assertEqual(conflicted["reason_code"], B20A.E06_CLOCK_CONFLICT)

    def test_each_future_timestamp_is_caught_by_its_OWN_guard(self):
        """Isolated deliberately: with both stamps equal, either guard hides the other.

        A mutation sweep found exactly that — neutering the `recorded_unix_nanos` check changed
        nothing observable, because the heartbeat check fired on the same crafted record. A test
        passing for a neighbouring guard's reason is not testing the guard it names.
        """
        self.write_valid(recorded_unix_nanos=NOW + SECOND, heartbeat_unix_nanos=NOW)
        verdict = self.read(now=NOW)
        self.assertTrue(verdict["kill_switch_engaged"])
        self.assertEqual(verdict["reason_code"], B20A.E06_CLOCK_CONFLICT,
                         "a record CREATED in the future must be a clock conflict on its own")

        self.write_valid(recorded_unix_nanos=NOW, heartbeat_unix_nanos=NOW + SECOND)
        verdict = self.read(now=NOW)
        self.assertTrue(verdict["kill_switch_engaged"])
        self.assertEqual(verdict["reason_code"], B20A.E06_CLOCK_CONFLICT,
                         "a heartbeat from the future must be a clock conflict on its own")

    def test_a_non_integer_clock_is_a_clock_conflict(self):
        for bad in (1.5, "now", True, None):
            with self.subTest(now=bad):
                verdict = B20A.read_verdict(bad, state_path=self.state,
                                            receipt_path=self.receipts, env=SECRET)
                self.assertTrue(verdict["kill_switch_engaged"])
                self.assertEqual(verdict["reason_code"], B20A.E06_CLOCK_CONFLICT)

    def test_a_malformed_record_is_engaged(self):
        for body in ("[]", '{"engaged": true}', '{"schema_version": "1.0.0"}'):
            with self.subTest(body=body):
                self.state.write_text(body)
                self.assertEqual(self.read()["reason_code"], B20A.E10_MALFORMED_RECORD)

    def test_a_non_integer_generation_is_malformed(self):
        self.engage()
        record = json.loads(self.state.read_text())
        record["generation"] = "1"
        self.state.write_text(json.dumps(record))
        self.assertEqual(self.read()["reason_code"], B20A.E10_MALFORMED_RECORD)

    def test_an_explicitly_engaged_switch_reports_that_reason(self):
        self.engage(reason="the watcher died")
        verdict = self.read()
        self.assertTrue(verdict["kill_switch_engaged"])
        self.assertEqual(verdict["reason_code"], B20A.E09_EXPLICITLY_ENGAGED)

    def test_the_read_path_never_raises(self):
        """A read that raised would hand the decision back to the caller — the original gap."""
        for body in ("", "{ not json", "[]", '{"engaged": "yes"}', "null"):
            with self.subTest(body=body):
                self.state.write_text(body)
                self.assertTrue(self.read()["kill_switch_engaged"])

    def test_exactly_one_reason_code_is_not_engaged(self):
        self.assertNotIn(B20A.E00_CLEARED_BY_OPERATOR, B20A.ENGAGED_REASONS)
        self.assertEqual(len(set(B20A.ENGAGED_REASONS)), len(B20A.ENGAGED_REASONS))


class NeverAutoClearsTests(Fixture):
    def test_a_restart_does_not_clear_and_neither_does_time(self):
        """B19a: it never auto-clears on restart or timeout. Time may only ENGAGE."""
        self.engage(reason="halt")
        for elapsed in (0, SECOND, 3600 * SECOND, 86400 * SECOND):
            with self.subTest(elapsed=elapsed):
                # A fresh read is exactly what a restart does: no state is held in memory.
                self.assertTrue(self.read(now=NOW + elapsed)["kill_switch_engaged"])

    def test_time_can_only_move_a_cleared_switch_towards_engaged(self):
        self.engage()
        self.clear(expected=1)
        self.assertFalse(self.read(now=NOW)["kill_switch_engaged"])
        self.assertTrue(self.read(now=NOW + 3600 * SECOND)["kill_switch_engaged"])

    def test_deleting_the_state_engages_rather_than_freeing(self):
        self.engage()
        self.clear(expected=1)
        self.assertFalse(self.read()["kill_switch_engaged"])
        self.state.unlink()
        self.assertTrue(self.read()["kill_switch_engaged"])


class ClearingTests(Fixture):
    def test_clearing_requires_a_reason(self):
        self.engage()
        for reason in ("", "   ", None, 7):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(B20A.EmergencyRefused, "reason"):
                    self.clear(reason=reason, expected=1)

    def test_clearing_requires_an_operator(self):
        self.engage()
        with self.assertRaisesRegex(B20A.EmergencyRefused, "operator"):
            self.clear(operator="", expected=1)

    def test_clearing_requires_the_secret(self):
        self.engage()
        with self.assertRaisesRegex(B20A.EmergencyRefused, "authentication"):
            self.clear(expected=1, env={})

    def test_clearing_a_generation_someone_else_moved_is_refused(self):
        """Otherwise an operator clears a halt they never saw."""
        self.engage()
        self.engage(reason="a second, different fault")
        with self.assertRaisesRegex(B20A.EmergencyRefused, "not 1"):
            self.clear(expected=1)

    def test_a_successful_clear_increments_the_generation_and_is_readable(self):
        self.engage()
        record = self.clear(expected=1, reason="cause understood")
        self.assertEqual(record["generation"], 2)
        verdict = self.read()
        self.assertFalse(verdict["kill_switch_engaged"])
        self.assertEqual(verdict["reason_code"], B20A.E00_CLEARED_BY_OPERATOR)

    def test_generations_are_monotonic_across_engage_and_clear(self):
        seen = []
        for index in range(3):
            seen.append(self.engage(reason=f"fault {index}")["generation"])
            seen.append(self.clear(expected=seen[-1], reason=f"cleared {index}")["generation"])
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(len(set(seen)), len(seen))


class EngageTests(Fixture):
    def test_engaging_requires_a_reason_and_an_operator(self):
        with self.assertRaisesRegex(B20A.EmergencyRefused, "reason"):
            self.engage(reason=" ")
        with self.assertRaisesRegex(B20A.EmergencyRefused, "operator"):
            self.engage(operator=" ")

    def test_engaging_over_an_unreadable_state_refuses_rather_than_overwriting(self):
        self.state.write_text("{ corrupt")
        with self.assertRaisesRegex(B20A.EmergencyRefused, "unreadable"):
            self.engage()
        # And the switch still reads engaged, so refusing to write is not refusing to protect.
        self.assertTrue(self.read()["kill_switch_engaged"])

    def test_engaging_needs_no_strategy_rpc_or_signer(self):
        """The whole point: a control that is hard to pull is not a control.

        Nothing is injected, nothing is reachable, and the call still succeeds.
        """
        record = self.engage(reason="pull it")
        self.assertTrue(record["engaged"])
        self.assertEqual(record["generation"], 1)


class HeartbeatTests(Fixture):
    def test_a_heartbeat_can_never_clear_an_engaged_switch(self):
        self.engage()
        B20A.heartbeat(NOW + SECOND, state_path=self.state, receipt_path=self.receipts,
                       env=SECRET)
        self.assertTrue(self.read(now=NOW + SECOND)["kill_switch_engaged"])

    def test_the_heartbeat_leaves_the_ENGAGED_FLAG_ITSELF_untouched(self):
        """Reads the record directly, because the verdict cannot answer this question.

        A mutation sweep found the previous test surviving a heartbeat that set engaged=False:
        the read path still engaged, but via VERIFIER DISAGREEMENT with the receipt log, not
        because the heartbeat had refused to clear. The test named one guard and was kept alive
        by another, so it proved nothing about the heartbeat at all.
        """
        self.engage(reason="halt")
        before = json.loads(self.state.read_text())

        B20A.heartbeat(NOW + SECOND, state_path=self.state, receipt_path=self.receipts,
                       env=SECRET)

        after = json.loads(self.state.read_text())
        self.assertIs(after["engaged"], True, "the heartbeat cleared the switch")
        self.assertEqual(after["engaged"], before["engaged"])
        self.assertEqual(after["generation"], before["generation"])
        self.assertEqual(after["reason"], before["reason"])
        self.assertGreater(after["heartbeat_unix_nanos"], before["heartbeat_unix_nanos"])

    def test_a_heartbeat_does_not_bump_the_generation(self):
        """A heartbeat is not an operator action and must not look like one."""
        self.engage()
        before = B20A._current_generation(self.state)
        B20A.heartbeat(NOW + SECOND, state_path=self.state, receipt_path=self.receipts,
                       env=SECRET)
        self.assertEqual(B20A._current_generation(self.state), before)

    def test_a_heartbeat_keeps_a_cleared_switch_alive(self):
        self.engage()
        self.clear(expected=1)
        self.assertTrue(self.read(now=NOW + 61 * SECOND)["kill_switch_engaged"])
        B20A.heartbeat(NOW + 60 * SECOND, state_path=self.state, receipt_path=self.receipts,
                       env=SECRET)
        self.assertFalse(self.read(now=NOW + 61 * SECOND)["kill_switch_engaged"])

    def test_a_heartbeat_without_state_refuses(self):
        with self.assertRaisesRegex(B20A.EmergencyRefused, "no state"):
            B20A.heartbeat(NOW, state_path=self.state, receipt_path=self.receipts, env=SECRET)


class TwoIndependentVerifiersTests(Fixture):
    """B19a: two verifiers, and disagreement means engaged."""

    def test_a_cleared_state_with_no_receipt_disagrees_and_engages(self):
        self.engage()
        self.clear(expected=1)
        self.receipts.unlink()
        verdict = self.read()
        self.assertTrue(verdict["kill_switch_engaged"])
        self.assertEqual(verdict["reason_code"], B20A.E08_VERIFIER_DISAGREEMENT)

    def test_a_rolled_back_receipt_log_disagrees_and_engages(self):
        self.engage()
        self.clear(expected=1)
        lines = self.receipts.read_text().splitlines()
        self.receipts.write_text(lines[0] + "\n")
        verdict = self.read()
        self.assertTrue(verdict["kill_switch_engaged"])
        self.assertEqual(verdict["reason_code"], B20A.E08_VERIFIER_DISAGREEMENT)

    def test_an_unreadable_receipt_log_disagrees_and_engages(self):
        self.engage()
        self.clear(expected=1)
        self.receipts.write_text("{ not json\n")
        self.assertEqual(self.read()["reason_code"], B20A.E08_VERIFIER_DISAGREEMENT)

    def test_agreement_is_required_on_the_generation_not_merely_the_flag(self):
        self.engage()
        self.clear(expected=1)
        tail = json.loads(self.receipts.read_text().splitlines()[-1])
        tail["generation"] = 99
        self.receipts.write_text(json.dumps(tail) + "\n")
        self.assertEqual(self.read()["reason_code"], B20A.E08_VERIFIER_DISAGREEMENT)

    def test_a_single_reader_could_not_see_these(self):
        """The justification for a second verifier, made concrete.

        The state file alone verifies perfectly in every case above — correct MAC, fresh
        heartbeat, engaged=False. Only the receipt log contradicts it.
        """
        self.engage()
        self.clear(expected=1)
        self.receipts.unlink()
        primary = B20A._read_record(self.state, B20A._secret(SECRET), NOW, 60 * SECOND)
        self.assertFalse(primary["kill_switch_engaged"])
        self.assertTrue(self.read()["kill_switch_engaged"])


class ReceiptTests(Fixture):
    def test_every_transition_appends_and_nothing_is_rewritten(self):
        self.engage(reason="one")
        first = self.receipts.read_text()
        self.clear(expected=1, reason="two")
        second = self.receipts.read_text()
        self.assertTrue(second.startswith(first), "the receipt log was rewritten, not appended")
        self.assertEqual(len(second.splitlines()), 2)

    def test_receipts_carry_the_reason_and_operator(self):
        self.engage(reason="the watcher died", operator="anont")
        receipt = json.loads(self.receipts.read_text().splitlines()[-1])
        self.assertEqual(receipt["reason"], "the watcher died")
        self.assertEqual(receipt["operator"], "anont")
        self.assertEqual(receipt["action"], "engage")

    def test_the_receipt_is_written_before_the_state(self):
        """If the process dies between them the verifiers disagree, which engages.

        The other order could leave a cleared state file with nothing attesting it.
        """
        self.engage()
        self.clear(expected=1)
        self.state.unlink()
        self.assertTrue(self.read()["kill_switch_engaged"])


class SecretHandlingTests(Fixture):
    def test_the_secret_never_appears_in_the_record_or_the_receipts(self):
        self.engage(reason="a fault")
        self.clear(expected=1, reason="reviewed")
        secret = SECRET[B20A.OPERATOR_SECRET_ENV]
        self.assertNotIn(secret, self.state.read_text())
        self.assertNotIn(secret, self.receipts.read_text())

    def test_the_secret_never_appears_in_a_verdict_or_a_snapshot(self):
        self.engage()
        verdict = self.read()
        secret = SECRET[B20A.OPERATOR_SECRET_ENV]
        self.assertNotIn(secret, json.dumps(verdict))
        self.assertNotIn(secret, json.dumps(B20A.snapshot(verdict)))

    def test_the_module_reads_the_secret_from_the_environment_only(self):
        source = (ROOT / "scripts" / "b20a_emergency_state.py").read_text()
        self.assertIn("os.environ", source)
        self.assertNotIn("argparse", source,
                         "a secret must never be reachable through argv")


class ConsoleBoundaryTests(Fixture):
    def test_the_snapshot_is_read_only_and_says_so(self):
        self.engage()
        snapshot = B20A.snapshot(self.read())
        self.assertIs(snapshot["console_may_mutate_this"], False)
        self.assertNotIn("mac", snapshot)

    def test_this_slice_added_no_write_path_to_the_console_or_its_server(self):
        """G6's caution: the console's read-only property is what makes it checkable by reading."""
        for name in ("ui/operator_console.html", "scripts/b12b_preview_server.py"):
            with self.subTest(name=name):
                self.assertNotIn("b20a", (ROOT / name).read_text().lower())


class FeedsTheRiskGovernorTests(Fixture):
    """The point of the slice: the field b12a demands now has a producer."""

    def base_health(self):
        return {"evidence_complete": True, "evidence_conflicting": False,
                "program_version_supported": True, "curve_regime_consistent": True,
                "evidence_slot": 435_600_000, "current_slot": 435_600_003,
                "evidence_unix": 1_785_600_000, "current_unix": 1_785_600_002, "provenance": {}}

    def test_the_produced_fields_satisfy_assert_health(self):
        self.engage()
        health = dict(self.base_health(), **B20A.health_fields(self.read()))
        self.assertIs(B12A.assert_health(health), health)

    def test_an_engaged_switch_makes_b12a_reject_with_R02(self):
        self.engage(reason="halt")
        health = dict(self.base_health(), **B20A.health_fields(self.read()))
        self.assertTrue(health["kill_switch_engaged"])
        reasons = B12A._health_reasons(
            health, {"max_evidence_age_slots": 10, "max_evidence_age_seconds": 5})
        self.assertIn(B12A.R02_KILL_SWITCH_ENGAGED, reasons)
        self.assertIn(B12A.R01_EMERGENCY_STATE, reasons)

    def test_no_state_at_all_still_produces_a_usable_engaged_health_block(self):
        """The absence case: with nothing on disk the governor still gets a decidable answer."""
        health = dict(self.base_health(), **B20A.health_fields(self.read()))
        B12A.assert_health(health)
        self.assertTrue(health["kill_switch_engaged"])
        self.assertTrue(health["emergency_state"])


class NoExecutionSurfaceTests(unittest.TestCase):
    def test_this_module_has_no_wallet_key_signing_or_submission_surface(self):
        """Checked with B17a's AST scanner rather than asserted in a docstring."""
        result = B17A.assert_no_execution_surface(entry="b20a_emergency_state.py")
        self.assertEqual(result["closure"], ["b20a_emergency_state.py"])
        self.assertEqual(result["execution_surface_found"], {})

    def test_no_float_appears_in_the_module(self):
        source = (ROOT / "scripts" / "b20a_emergency_state.py").read_text()
        self.assertNotIn("float(", source)
        self.assertNotIn("time.time()", source,
                         "a control process whose behaviour depends on an unstated clock cannot "
                         "be tested at its boundaries")


if __name__ == "__main__":
    unittest.main()
