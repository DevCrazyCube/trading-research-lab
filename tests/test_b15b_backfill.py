"""B15b — the backfill guards and the derivation, each shown to be able to refuse.

Every transaction here is manufactured. No network is touched: the transport takes an injected
opener, and the tests that exercise failure rules build responses by hand.

The determination under test is the one frozen before any fetch: `real_quote` is provable only
when the launch transaction carries a TradeEvent, and `complete` is provable from the absence of a
CompleteEvent in the transaction that created the curve.
"""
import base64
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15B = _load("b15b_backfill", "b15b_backfill.py")
# One module graph, through the worker.
PILOT = B15B.PILOT
FIXTURES = _load("b15a_shadow_fixtures", "b15a_shadow_fixtures.py")
Refused = B15B.BackfillRefused

MINT = "1thX6LZfHDZZbBQTG5s2XkvGXqivXhSpqSGuKAM1oV5"


def _restore_env(name, previous):
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


def event_log(payload):
    return f"{PILOT.PROGRAM_DATA_PREFIX}{base64.b64encode(payload).decode()}"


def trade_payload(mint, real_quote=1_000_000_000, virtual_quote=31_000_000_000,
                  virtual_token=1_000_000_000_000, real_token=700_000_000_000):
    """A TradeEvent built from the PINNED IDL, so it cannot drift from the decoder it exercises."""
    decoder = B15B.build_decoder()
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    discriminator = bytes(next(e["discriminator"] for e in idl["events"]
                               if e["name"] == "TradeEvent"))
    types = decoder["types"]
    body = bytearray(discriminator)
    overrides = {"mint": mint, "real_quote_reserves": real_quote,
                 "virtual_quote_reserves": virtual_quote,
                 "virtual_token_reserves": virtual_token, "real_token_reserves": real_token}
    for field in types["TradeEvent"]["type"]["fields"]:
        body += _encode_field(field, types, overrides)
    return bytes(body)


def complete_payload(mint):
    decoder = B15B.build_decoder()
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    discriminator = bytes(next(e["discriminator"] for e in idl["events"]
                               if e["name"] == "CompleteEvent"))
    types = decoder["types"]
    body = bytearray(discriminator)
    for field in types["CompleteEvent"]["type"]["fields"]:
        body += _encode_field(field, types, {"mint": mint})
    return bytes(body)


def _encode_field(field, types, overrides):
    name, kind = field["name"], field["type"]
    if name in overrides:
        value = overrides[name]
        if kind in ("pubkey", "publicKey"):
            return FIXTURES.PILOT.load_pinned_create_type() and _pubkey(value)
        return int(value).to_bytes(8, "little")
    return _zero(kind, types)


def _pubkey(value):
    import importlib
    b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
    return b7d.b58decode(value)


def _zero(kind, types):
    if isinstance(kind, dict) and "vec" in kind:
        return (0).to_bytes(4, "little")
    if isinstance(kind, dict) and "defined" in kind:
        name = kind["defined"]
        name = name.get("name") if isinstance(name, dict) else name
        return b"".join(_zero(f["type"], types) for f in types[name]["type"]["fields"])
    return {"string": (0).to_bytes(4, "little"), "pubkey": bytes(32), "publicKey": bytes(32),
            "bool": b"\x00", "u8": b"\x00", "u16": bytes(2), "u32": bytes(4), "u64": bytes(8),
            "i64": bytes(8), "u128": bytes(16)}[kind]


def create_logs(mint, with_trade=False, with_complete=False, **trade_kwargs):
    b7d, disc, create_type, types = PILOT.load_pinned_create_type()
    body = bytearray(disc)
    for field in create_type["type"]["fields"]:
        body += _encode_field(field, types, {"mint": mint, "virtual_sol_reserves": 30_000_000_000,
                                             "virtual_token_reserves": 1_000_000_000_000,
                                             "real_token_reserves": 800_000_000_000})
    logs = [event_log(bytes(body))]
    if with_trade:
        logs.append(event_log(trade_payload(mint, **trade_kwargs)))
    if with_complete:
        logs.append(event_log(complete_payload(mint)))
    return logs


def response(mint, signature="Sig1", slot=1000, err=None, **kwargs):
    return {"result": {"slot": slot,
                       "transaction": {"signatures": [signature]},
                       "meta": {"err": err, "logMessages": create_logs(mint, **kwargs)}}}


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15b-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15b"
        self.work.mkdir()


class TestGates(Temp):
    def test_the_committed_freeze_verifies(self):
        document = B15B.verify_preregistration()
        self.assertEqual("B15B_LAUNCH_BACKFILL_V1", document["preregistration_id"])
        self.assertTrue(document["reads_only"])

    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a different worker"):
            B15B.verify_preregistration(expected_sha256="0" * 64)

    def test_a_missing_freeze_is_refused_as_a_refusal(self):
        with self.assertRaises(Refused):
            B15B.verify_preregistration(path=self.directory / "absent.json")

    def test_no_execution_surface(self):
        self.assertTrue(B15B.assert_no_execution_surface())

    def test_a_planted_execution_surface_is_caught(self):
        for token in ("sendTransaction", "signTransaction", "simulateTransaction", "Keypair"):
            with self.subTest(token=token):
                planted = self.directory / f"p_{token}.py"
                planted.write_text(f"x = {token}\n")
                with self.assertRaises(Refused):
                    B15B.assert_no_execution_surface(planted)

    def test_writing_into_b15a_or_b11a_is_refused(self):
        for marker in ("b15a", "b11a"):
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    B15B.assert_isolated(ROOT / "research" / marker / "b15b")

    def test_a_directory_that_is_not_b15b_is_refused(self):
        with self.assertRaisesRegex(Refused, "must be .../b15b"):
            B15B.assert_isolated(self.directory / "elsewhere")

    def test_a_missing_credential_is_refused_not_defaulted(self):
        previous = os.environ.pop("SOLANA_RPC_URL", None)
        self.addCleanup(_restore_env, "SOLANA_RPC_URL", previous)
        with self.assertRaisesRegex(Refused, "environment-only"):
            B15B.rpc_url()

    def test_the_receipt_is_scheme_and_host_only(self):
        receipt = B15B.endpoint_receipt("https://host.example.com/x?api-key=SECRET")
        self.assertEqual("https://host.example.com", receipt)
        self.assertNotIn("SECRET", receipt)

    def test_an_endpoint_with_no_host_is_refused(self):
        for bad in ("not-a-url", "", "/just/a/path"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(Refused, "no scheme or host"):
                    B15B.endpoint_receipt(bad)


class TestProvabilityDetermination(Temp):
    """The question Codex asked, answered from evidence and pinned by tests."""

    def test_real_quote_is_provable_when_the_launch_tx_carries_a_trade(self):
        events = B15B.curve_events(response(MINT, with_trade=True, real_quote=4242),
                                   B15B.build_decoder())
        state, missing, trades = B15B.derive_t0_state(events, MINT, 1000)
        self.assertEqual(1, trades)
        self.assertEqual(4242, state["real_quote"])
        self.assertEqual([], missing, "every t0 field should be present with a trade")

    def test_real_quote_is_unavailable_with_no_trade_and_is_never_zero(self):
        events = B15B.curve_events(response(MINT), B15B.build_decoder())
        state, missing, trades = B15B.derive_t0_state(events, MINT, 1000)
        self.assertEqual(0, trades)
        self.assertIsNone(state.get("real_quote"))
        self.assertEqual(["real_quote"], missing)
        self.assertNotEqual(0, state.get("real_quote"),
                            "a curve that holds nothing and a curve we cannot measure differ")

    def test_complete_is_false_without_a_complete_event(self):
        """Evidence, not convention: the curve is created in this very transaction."""
        events = B15B.curve_events(response(MINT, with_trade=True), B15B.build_decoder())
        state, _missing, _trades = B15B.derive_t0_state(events, MINT, 1000)
        self.assertFalse(state["complete"])

    def test_complete_is_true_with_a_complete_event(self):
        events = B15B.curve_events(response(MINT, with_trade=True, with_complete=True),
                                   B15B.build_decoder())
        state, _missing, _trades = B15B.derive_t0_state(events, MINT, 1000)
        self.assertTrue(state["complete"])

    def test_the_last_trade_wins_because_t0_is_the_terminal_state(self):
        decoder = B15B.build_decoder()
        logs = create_logs(MINT, with_trade=True, real_quote=100)
        logs.append(event_log(trade_payload(MINT, real_quote=900)))
        events = B15B.curve_events(
            {"result": {"slot": 1000, "transaction": {"signatures": ["Sig1"]},
                        "meta": {"err": None, "logMessages": logs}}}, decoder)
        state, _missing, trades = B15B.derive_t0_state(events, MINT, 1000)
        self.assertEqual(2, trades)
        self.assertEqual(900, state["real_quote"])


class TestFailureRules(Temp):
    def test_a_signature_mismatch_fails_visibly(self):
        with self.assertRaisesRegex(Refused, B15B.F01_SIGNATURE_MISMATCH):
            B15B.validate_response(response(MINT, signature="Other"), "Sig1", 1000)

    def test_a_slot_mismatch_fails_visibly(self):
        with self.assertRaisesRegex(Refused, B15B.F02_SLOT_MISMATCH):
            B15B.validate_response(response(MINT, slot=999), "Sig1", 1000)

    def test_a_failed_transaction_fails_visibly(self):
        with self.assertRaisesRegex(Refused, B15B.F04_TRANSACTION_FAILED):
            B15B.validate_response(response(MINT, err={"X": 1}), "Sig1", 1000)

    def test_a_stale_response_fails_visibly(self):
        payload = response(MINT)
        payload["context"] = {"slot": 1}
        with self.assertRaisesRegex(Refused, B15B.F07_STALE_RESPONSE):
            B15B.validate_response(payload, "Sig1", 1000)

    def test_a_valid_response_passes(self):
        self.assertEqual(1000, B15B.validate_response(response(MINT), "Sig1", 1000))

    def test_a_missing_create_event_fails_visibly(self):
        events = B15B.curve_events(
            {"result": {"meta": {"logMessages": []}}}, B15B.build_decoder())
        with self.assertRaisesRegex(Refused, B15B.F05_NO_CREATE_EVENT):
            B15B.derive_t0_state(events, MINT, 1000)

    def test_a_mint_mismatch_surfaces_as_no_create_event(self):
        """The honest code for it. A CreateEvent for another mint is not a CreateEvent for this
        curve, so the population is empty and F05 fires; a separate F03 comparison after filtering
        on the same field could never be false, so it is not made."""
        events = B15B.curve_events(response(MINT), B15B.build_decoder())
        with self.assertRaisesRegex(Refused, B15B.F05_NO_CREATE_EVENT):
            B15B.derive_t0_state(events, "SomeOtherMint", 1000)

    def test_an_undecodable_known_event_fails_visibly(self):
        """A known discriminator whose body is truncated: F09, not a silent skip."""
        truncated = trade_payload(MINT)[:12]
        events_response = {"result": {"meta": {"logMessages": [event_log(truncated)]}}}
        with self.assertRaisesRegex(Refused, B15B.F09_UNKNOWN_DISCRIMINATOR):
            B15B.curve_events(events_response, B15B.build_decoder())

    def test_an_unrecognised_discriminator_is_recorded_not_raised(self):
        """Foreign events are expected traffic; only a KNOWN event failing to decode is a fault."""
        foreign = bytes.fromhex("aabbccddeeff0011") + b"\x00" * 40
        events = B15B.curve_events(
            {"result": {"meta": {"logMessages": [event_log(foreign)]}}}, B15B.build_decoder())
        self.assertEqual(1, len(events))
        self.assertIsNone(events[0]["name"])

    def test_two_create_events_for_one_mint_fail_visibly(self):
        logs = create_logs(MINT) + create_logs(MINT)
        events = B15B.curve_events(
            {"result": {"meta": {"logMessages": logs}}}, B15B.build_decoder())
        with self.assertRaisesRegex(Refused, B15B.F06_CONFLICTING_EVENTS):
            B15B.derive_t0_state(events, MINT, 1000)

    def test_two_complete_events_fail_visibly(self):
        logs = create_logs(MINT, with_complete=True)
        logs.append(event_log(complete_payload(MINT)))
        events = B15B.curve_events(
            {"result": {"meta": {"logMessages": logs}}}, B15B.build_decoder())
        with self.assertRaisesRegex(Refused, B15B.F06_CONFLICTING_EVENTS):
            B15B.derive_t0_state(events, MINT, 1000)


class TestTransport(Temp):
    def _policy(self):
        return B15B.verify_preregistration()

    def test_a_successful_fetch_is_preserved_and_returned(self):
        log = B15B.ExchangeLog(self.work / "x.jsonl")
        self.addCleanup(log.close)
        payload = response(MINT)

        class Handle:
            status = 200

            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        outcome, document, latency = B15B.fetch_transaction(
            "Sig1", "https://h.invalid/?k=1", self._policy(), log,
            opener=lambda *_a, **_k: Handle(), sleeper=lambda _s: None)
        self.assertEqual("retrieved", outcome)
        self.assertEqual(payload, document)
        self.assertGreater(latency, 0)
        self.assertEqual(1, log.count)

    def test_retries_are_bounded_and_every_attempt_is_preserved(self):
        log = B15B.ExchangeLog(self.work / "x.jsonl")
        self.addCleanup(log.close)

        def opener(*_a, **_k):
            raise TimeoutError("timed out")

        outcome, _payload, _latency = B15B.fetch_transaction(
            "Sig1", "https://h.invalid/?k=1", self._policy(), log, opener=opener,
            sleeper=lambda _s: None)
        self.assertEqual("transport_error", outcome)
        attempts = self._policy()["rate_and_stopping_policy"]["max_attempts_per_signature"]
        self.assertEqual(attempts, log.count, "every attempt must be preserved")

    def test_a_non_retryable_error_stops_immediately(self):
        log = B15B.ExchangeLog(self.work / "x.jsonl")
        self.addCleanup(log.close)

        def opener(*_a, **_k):
            raise ValueError("malformed request")

        B15B.fetch_transaction("Sig1", "https://h.invalid/?k=1", self._policy(), log,
                               opener=opener, sleeper=lambda _s: None)
        self.assertEqual(1, log.count, "a non-retryable error must not be retried")

    def test_the_credential_never_reaches_the_exchange_log(self):
        log = B15B.ExchangeLog(self.work / "x.jsonl")

        def opener(*_a, **_k):
            raise TimeoutError("timed out")

        B15B.fetch_transaction("Sig1", "https://h.invalid/path?api-key=SUPERSECRET",
                               self._policy(), log, opener=opener, sleeper=lambda _s: None)
        log.close()
        blob = (self.work / "x.jsonl").read_text()
        self.assertNotIn("SUPERSECRET", blob)
        self.assertNotIn("api-key", blob)
        self.assertIn("https://h.invalid", blob)

    def test_the_retryable_marker_test_is_case_insensitive(self):
        markers = self._policy()["rate_and_stopping_policy"]["retryable_markers"]
        self.assertTrue(B15B.is_retryable("Connection Reset by peer", markers))
        self.assertFalse(B15B.is_retryable("malformed request", markers))

    def test_the_rate_policy_is_the_frozen_one(self):
        rate = self._policy()["rate_and_stopping_policy"]
        self.assertEqual(2, rate["max_requests_per_second"])
        self.assertEqual(1, rate["max_concurrent_requests"])
        self.assertEqual(4, rate["max_attempts_per_signature"])


class TestExactSummaries(Temp):
    def test_order_statistics_are_exact_integers(self):
        summary = B15B._summary([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(10, summary["count"])
        self.assertEqual(1, summary["min"])
        self.assertEqual(10, summary["max"])
        for key in ("p50", "p90", "p99"):
            with self.subTest(key=key):
                self.assertIsInstance(summary[key], int)
                self.assertIn(summary[key], range(1, 11))

    def test_no_interpolation_between_neighbours(self):
        """An interpolated percentile invents a value that no observation had."""
        values = [10, 20]
        self.assertIn(B15B._summary(values)["p50"], values)

    def test_an_empty_summary_says_so_rather_than_reporting_zero(self):
        self.assertEqual({"count": 0}, B15B._summary([]))


class TestEndToEndSynthetic(Temp):
    """The whole worker against a fake opener and a synthetic B15a database."""

    def setUp(self):
        super().setUp()
        self.b15a = self.directory / "shadow.sqlite"
        source = sqlite3.connect(self.b15a)
        source.executescript(PILOT.SCHEMA)
        for seq, (signature, mint) in enumerate(
                [("SigTrade", MINT), ("SigNoTrade", MINT)], start=1):
            source.execute(
                "INSERT INTO launch(launch_seq,session_id,frame_seq,signature,slot,mint,"
                "decoded_wall_unix,decoded_monotonic_ns,decode_status,evidence_sha256,create_key) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (seq, "s", seq, signature, 1000, mint, 0.0, 0, PILOT.DECODE_DECODED, "e",
                 f"k{seq}"))
        source.commit()
        source.close()

    def _run(self, **kwargs):
        def opener(request, **_k):
            body = json.loads(request.data.decode())
            signature = body["params"][0]
            payload = response(MINT, signature=signature,
                               with_trade=(signature == "SigTrade"))

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        return B15B.run(b15a_path=self.b15a, work_dir=self.work, opener=opener,
                        sleeper=lambda _s: None, url="https://h.invalid/?api-key=SECRET",
                        **kwargs)

    def test_the_trade_launch_resolves_and_the_other_is_unavailable(self):
        counts = self._run()
        self.assertEqual(2, counts["attempted"])
        self.assertEqual(1, counts["retrieved"])
        self.assertEqual(1, counts["unavailable"])
        self.assertEqual(0, counts["failed"])
        self.assertEqual(1, counts["state_complete"])
        self.assertIn(B15B.U01_REAL_QUOTE_NOT_PUBLISHED, counts["reasons"])

    def test_no_hypothetical_entry_is_proposed_without_stated_costs(self):
        """The path that matters: t0 complete, no veto fires, and STILL no entry.

        Reserves here are realistic on purpose. The first version used tiny ones and B11b's real
        veto set fired V6_order_exceeds_real_token_reserve, which is correct behaviour but meant
        the test never reached the cost rule it was written for.
        """
        counts = self._run()
        self.assertEqual(0, counts["hypothetical_entries"])
        database = sqlite3.connect(self.work / "backfill.sqlite")
        reasons = dict(database.execute(
            "SELECT reason_code, COUNT(*) FROM decision_v2 GROUP BY 1"))
        database.close()
        self.assertTrue(any(B15B.U04_COST_INPUTS_UNSTATED in key for key in reasons), reasons)

    def test_history_is_not_rewritten_and_the_new_decision_is_version_two(self):
        self._run()
        database = sqlite3.connect(self.work / "backfill.sqlite")
        rows = database.execute(
            "SELECT version, evidence_basis FROM decision_v2").fetchall()
        database.close()
        self.assertTrue(rows)
        for version, basis in rows:
            self.assertEqual(2, version)
            self.assertEqual(B15B.BASIS_BACKFILLED, basis)

    def test_one_decision_per_decoded_launch(self):
        self._run()
        database = sqlite3.connect(self.work / "backfill.sqlite")
        per = database.execute(
            "SELECT signature, COUNT(*) FROM decision_v2 GROUP BY 1").fetchall()
        database.close()
        for _signature, count in per:
            self.assertEqual(1, count)

    def test_the_run_is_idempotent(self):
        first = self._run()
        second = self._run()
        self.assertEqual(2, first["attempted"])
        self.assertEqual(0, second["attempted"], "a resolved signature must not be refetched")
        database = sqlite3.connect(self.work / "backfill.sqlite")
        self.assertEqual(2, database.execute("SELECT COUNT(*) FROM backfill").fetchone()[0])
        database.close()

    def test_b15a_is_never_written(self):
        before = self.b15a.read_bytes()
        self._run()
        self.assertEqual(before, self.b15a.read_bytes(),
                         "B15a is append-only evidence and this worker may only read it")

    def test_no_credential_reaches_any_artifact(self):
        self._run()
        for path in (self.work / "backfill.sqlite", self.work / "rpc_exchanges.jsonl"):
            with self.subTest(path=path.name):
                self.assertNotIn(b"SECRET", path.read_bytes())

    def test_the_status_line_is_redacted(self):
        self._run()
        report = B15B.status(db_path=self.work / "backfill.sqlite")
        PILOT.assert_redacted(report)
        self.assertTrue(report["reads_only"])
        self.assertEqual("never_executed", report["execution_status"])
        self.assertEqual(1, report["launches_with_a_trade_in_the_launch_tx"])


if __name__ == "__main__":
    unittest.main()
