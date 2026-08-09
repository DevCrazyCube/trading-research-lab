"""Tests for the Telegram notifier. Nothing here touches the network.

The interesting surface is not "does it send" -- it is "what can it be made to send". The state
file, the logs and the receipts all reference an RPC URL whose PATH carries a credential, so the
tests that matter are the ones that try to get that key out through the notifier.
"""
import importlib.util
import json
import os
import pathlib
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("operator_notify", ROOT / "scripts" / "operator_notify.py")
N = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(N)

KEY = "abcd1234efgh5678ijkl9012mnop3456"
URL = f"https://solana-mainnet.core.chainstack.com/{KEY}"


class TheCredentialGuard(unittest.TestCase):
    """A path-embedded key is the shape a netloc-only sanitiser misses, and it is the shape we have."""

    def setUp(self):
        self.secrets = {URL, KEY}

    def test_the_whole_url_is_refused(self):
        with self.assertRaisesRegex(N.NotifyRefused, "contains a credential"):
            N.assert_no_secret(f"collection failed against {URL}", self.secrets)

    def test_the_path_segment_alone_is_refused(self):
        """The likelier leak: somebody quotes a log line that carries only the key."""
        with self.assertRaisesRegex(N.NotifyRefused, "contains a credential"):
            N.assert_no_secret(f"request to .../{KEY} timed out", self.secrets)

    def test_a_clean_message_passes(self):
        self.assertIsNone(N.assert_no_secret("stage complete: build_cohort [3/9]", self.secrets))

    def test_the_refusal_does_not_repeat_the_secret(self):
        """A refusal that echoes what it caught has leaked it into the log it refused to leak to."""
        with self.assertRaises(N.NotifyRefused) as caught:
            N.assert_no_secret(f"boom {KEY}", self.secrets)
        self.assertNotIn(KEY, str(caught.exception))

    def test_secret_values_finds_a_path_embedded_key(self):
        import os
        os.environ["SOLANA_RPC_URL"] = URL
        self.addCleanup(os.environ.pop, "SOLANA_RPC_URL", None)
        self.assertIn(KEY, N.secret_values())
        self.assertIn(URL, N.secret_values())

    def test_the_bot_token_is_itself_a_secret(self):
        """A notifier that can leak its own credential is not better than one that leaks the other."""
        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456:AAF-verylongtokenvalue"
        self.addCleanup(os.environ.pop, "TELEGRAM_BOT_TOKEN", None)
        self.assertIn("123456:AAF-verylongtokenvalue", N.secret_values())

    def test_send_refuses_BEFORE_opening_a_connection(self):
        """The guard has to precede the request, or the secret is already on the wire."""
        import os
        os.environ["SOLANA_RPC_URL"] = URL
        self.addCleanup(os.environ.pop, "SOLANA_RPC_URL", None)
        def opener(*_args, **_kwargs):
            raise AssertionError("a connection was opened despite the credential")
        with self.assertRaises(N.NotifyRefused):
            N.send(f"leak {KEY}", token="t", chat_id="1", opener=opener)

    def test_a_guard_that_knows_no_secrets_refuses_rather_than_passing_everything(self):
        """The hole the test above found in the first draft.

        With nothing credential-shaped in the environment the secret set is EMPTY, so every
        message matched nothing and the guard passed everything while appearing to work. That is
        a check that cannot fire, which is worse than no check because the absent one is visible.
        """
        # A CLEARED environment, not merely one with two names removed. The real shell carries
        # SSH_AUTH_SOCK and friends, which match the AUTH marker and are long enough to count, so
        # popping two names leaves the secret set non-empty and the test passes for the wrong
        # reason -- it would prove nothing about the empty case it claims to cover.
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(N.secret_values(), "the fixture must actually have no secrets visible")
            with self.assertRaisesRegex(N.NotifyRefused, "no credentials are visible"):
                N.assert_no_secret("a perfectly innocent message")

    def test_it_does_not_open_a_connection_when_it_cannot_verify(self):
        def opener(*_args, **_kwargs):
            raise AssertionError("a connection was opened without a verifiable message")
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(N.NotifyRefused):
                N.send("innocent", token="t", chat_id="1", opener=opener)


class WhatItIsAllowedToSay(unittest.TestCase):
    def test_describe_names_fields_and_never_carries_the_endpoint(self):
        """`describe` is a whitelist. A state that grows a field must not export it by inheritance."""
        state = {"state": "running_stage", "stage_in_flight": "build_cohort",
                 "stages_completed": ["program_boundary"], "quarantine": None,
                 "polls": 3, "last_tip_slot": 437000000,
                 "endpoint": URL, "some_future_field": KEY}
        described = N.describe(state, ["program_boundary"])
        flattened = json.dumps(described)
        self.assertNotIn(URL, flattened)
        self.assertNotIn(KEY, flattened)
        self.assertEqual(described["stage_in_flight"], "build_cohort")

    def test_a_quarantine_is_reported_by_code_and_stage(self):
        state = {"state": "quarantined", "stage_in_flight": None, "stages_completed": [],
                 "quarantine": {"reason_code": "Q07_stage_failed", "stage": "signature_inventory"}}
        described = N.describe(state, [])
        self.assertEqual(described["quarantine_reason"], "Q07_stage_failed")
        self.assertEqual(described["quarantine_stage"], "signature_inventory")


class WhenItSpeaks(unittest.TestCase):
    """Quiet by default. A notifier that pings on every heartbeat gets muted, and the muted alert
    is the quarantine."""

    BASE = {"state": "running_stage", "stage_in_flight": "enumerate_creates",
            "stages_completed": ["program_boundary"], "receipts": [], "quarantine_reason": None,
            "quarantine_stage": None, "polls": 1, "last_tip_slot": 1,
            "watcher_running": True, "stalled_seconds": 12}

    def test_an_unchanged_state_says_nothing(self):
        self.assertIsNone(N.render(self.BASE, dict(self.BASE)))

    def test_a_heartbeat_alone_says_nothing(self):
        moved = dict(self.BASE, polls=99, last_tip_slot=437_999_999)
        self.assertIsNone(N.render(self.BASE, moved),
                          "polls and tip advance constantly; they are not events")

    def test_a_quarantine_is_announced(self):
        hit = dict(self.BASE, state="quarantined", quarantine_reason="Q07_stage_failed",
                   quarantine_stage="signature_inventory")
        message = N.render(self.BASE, hit)
        self.assertIn("QUARANTINED", message)
        self.assertIn("Q07_stage_failed", message)

    def test_a_completed_stage_is_announced_with_progress(self):
        done = dict(self.BASE, stages_completed=["program_boundary", "enumerate_creates"])
        message = N.render(self.BASE, done)
        self.assertIn("enumerate_creates", message)
        self.assertIn("2/9", message)

    def test_a_dead_watcher_with_a_cold_heartbeat_is_announced(self):
        """The blind spot that cost 95 minutes: a dead watcher changes no state, so every
        change-driven check stayed silent while the collection sat stopped."""
        dead = dict(self.BASE, watcher_running=False, stalled_seconds=5400)
        message = N.render(self.BASE, dead)
        self.assertIn("STALLED", message)
        self.assertIn("90 minutes", message)

    def test_a_stall_is_announced_once_not_every_interval(self):
        """An alert that repeats every minute is one that gets muted, and this is the alert that
        matters overnight."""
        dead = dict(self.BASE, watcher_running=False, stalled_seconds=5400)
        self.assertIn("STALLED", N.render(self.BASE, dead))
        later = dict(dead, stalled_seconds=5460)
        self.assertIsNone(N.render(dead, later), "the same stall must not re-announce")

    def test_a_watcher_that_exits_cleanly_is_reported_without_the_stall_wording(self):
        gone = dict(self.BASE, watcher_running=False, stalled_seconds=30)
        message = N.render(self.BASE, gone)
        self.assertIn("watcher process is gone", message)
        self.assertNotIn("STALLED", message)

    def test_a_cold_heartbeat_with_a_LIVE_watcher_is_not_a_stall(self):
        """A long stage legitimately goes quiet between heartbeats; only a MISSING process counts."""
        quiet = dict(self.BASE, watcher_running=True, stalled_seconds=5400)
        self.assertIsNone(N.render(self.BASE, quiet))

    def test_the_first_observation_reports_where_things_stand(self):
        message = N.render(None, self.BASE)
        self.assertIn("running_stage", message)


class TheWatcherDoesNotInterfere(unittest.TestCase):
    def test_a_transport_failure_does_not_stop_the_watch(self):
        """A phone that cannot be reached is not a reason to stop watching a five-day collection."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            path.write_text(json.dumps({"state": "running_stage", "stages_completed": [],
                                        "stage_in_flight": None, "quarantine": None}))
            def explode(_message):
                raise ConnectionError("no network")
            result = N.watch(state_path=path, receipt_dir=pathlib.Path(tmp) / "none",
                             sender=explode, once=True)
            self.assertEqual(result["state"], "running_stage")

    def test_a_credential_refusal_DOES_stop_the_watch(self):
        """The one exception. A transport failure is bad luck; a credential in an outbound message
        is a defect, and continuing would retry the leak every interval."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            path.write_text(json.dumps({"state": "x", "stages_completed": [],
                                        "stage_in_flight": None, "quarantine": None}))
            def refuse(_message):
                raise N.NotifyRefused("credential")
            with self.assertRaises(N.NotifyRefused):
                N.watch(state_path=path, receipt_dir=pathlib.Path(tmp) / "none",
                        sender=refuse, once=True)

    def test_it_reads_nothing_when_the_state_file_is_absent(self):
        self.assertIsNone(N.read_once(state_path=pathlib.Path("/nonexistent/state.json")))


class ItIsNotPartOfThePipeline(unittest.TestCase):
    def test_it_is_not_manifest_pinned(self):
        """Observers must not be pinned: pinning would make an edit to the notifier quarantine the
        collection, which inverts the relationship. It participates in nothing."""
        spec = importlib.util.spec_from_file_location("b11c", ROOT / "scripts" / "b11c_maturity_watcher.py")
        b11c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b11c)
        self.assertNotIn("scripts/operator_notify.py", b11c.MANIFEST_FILES)

    def test_it_names_no_write_of_its_own(self):
        source = (ROOT / "scripts" / "operator_notify.py").read_text()
        for forbidden in ("write_text(", "os.replace(", "shutil.", "executemany("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
