"""B15h — the prospective-entry guards, each shown to be able to refuse.

The failure that would matter most here is a quiet one: a pre-activation launch slipping into the
V2 population, which would be recovering a quarantined cell after its outcome was observable. The
rest are the same family — provenance rewritten as continuous, a missed target repaired from
current state, a V1 identifier merged in, an unreadable feed treated as clean.
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


B15H = _load("b15h_prospective_entry", "b15h_prospective_entry.py")
B15G, B15F, B15D, B15B, PILOT, B10A = (B15H.B15G, B15H.B15F, B15H.B15D, B15H.B15B, B15H.PILOT,
                                       B15H.B10A)
Refused = B15H.ProspectiveRefused

MINT = "1thX6LZfHDZZbBQTG5s2XkvGXqivXhSpqSGuKAM1oV5"
CURVE = "So11111111111111111111111111111111111111112"
DECODER = B15B.build_decoder()
ACTIVATION = B15H.verify_preregistration()["activation"]["activation_slot"]


def curve_account(complete=False, mayhem=False, real_token=700_000_000_000):
    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
    types = DECODER["types"]
    overrides = {"virtual_token_reserves": 1_000_000_000_000,
                 "virtual_quote_reserves": 31_000_000_000,
                 "real_token_reserves": real_token, "real_quote_reserves": 1_000_000_000,
                 "token_total_supply": 1_000_000_000_000_000, "complete": complete,
                 "creator": MINT, "is_mayhem_mode": mayhem, "is_cashback_coin": False,
                 "quote_mint": b9d.NATIVE_QUOTE_MINT}
    body = bytearray(B15F.BONDING_CURVE_DISCRIMINATOR)
    for field in types["BondingCurve"]["type"]["fields"]:
        name, kind = field["name"], field["type"]
        value = overrides[name]
        if kind in ("pubkey", "publicKey"):
            body += b7d.b58decode(value)
        elif kind == "bool":
            body += b"\x01" if value else b"\x00"
        else:
            body += int(value).to_bytes(8, "little")
    return bytes(body)


def trade_payload(fee_bps=95):
    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
    types = DECODER["types"]
    discriminator = bytes(next(e["discriminator"] for e in json.loads(
        (ROOT / "research" / "pump_idl_9c82f61.json").read_text())["events"]
        if e["name"] == "TradeEvent"))
    overrides = {"mint": MINT, "is_buy": True, "fee_basis_points": fee_bps,
                 "creator_fee_basis_points": 5, "cashback_fee_basis_points": 0,
                 "buyback_fee_basis_points": 0, "quote_mint": b9d.NATIVE_QUOTE_MINT}
    body = bytearray(discriminator)
    for field in types["TradeEvent"]["type"]["fields"]:
        name, kind = field["name"], field["type"]
        if name in overrides:
            value = overrides[name]
            if kind in ("pubkey", "publicKey"):
                body += b7d.b58decode(value)
            elif kind == "bool":
                body += b"\x01" if value else b"\x00"
            else:
                body += int(value).to_bytes(8, "little")
        else:
            body += _zero(kind, types)
    return bytes(body)


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


def batch_response(context_slot, curves, data=None, values=None):
    if values is None:
        values = [{"owner": B15F.PUMP_PROGRAM, "lamports": 1_000_000,
                   "data": [base64.b64encode(
                       data if data is not None else curve_account()).decode(), "base64"]}
                  for _ in curves]
    return {"result": {"context": {"slot": context_slot}, "value": values}}


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15h-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15h"
        self.work.mkdir()
        self.document = B15H.verify_preregistration()

    def b15a(self, launches, degraded=()):
        path = self.directory / "shadow.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(PILOT.SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO session(session_id,endpoint_scheme_host,commitment,started_wall_unix,"
            "started_monotonic_ns) VALUES ('s','wss://h','confirmed',0.0,0)")
        for index, (signature, slot) in enumerate(launches, start=1):
            connection.execute(
                "INSERT OR IGNORE INTO launch(launch_seq,session_id,frame_seq,signature,slot,mint,"
                "bonding_curve,decoded_wall_unix,decoded_monotonic_ns,decode_status,"
                "evidence_sha256,create_key) VALUES (?,?,?,?,?,?,?,0.0,0,?,'e',?)",
                (index, "s", index, signature, slot, MINT, CURVE, PILOT.DECODE_DECODED,
                 f"k{index}"))
            reason = (PILOT.S07_SESSION_DEGRADED if signature in degraded else PILOT.S04_VETO)
            connection.execute(
                "INSERT OR IGNORE INTO decision(launch_seq,policy_id,decided_wall_unix,decided_monotonic_ns,"
                "observation_to_decision_ns,feature_availability,policy_result,reason_code,"
                "evidence_sha256) VALUES (?,?,0.0,0,0,'{}',?,?,'e')",
                (index, "p", PILOT.RESULT_NO_ENTRY, reason))
        connection.commit()
        connection.close()
        return path

    def b15b(self, signatures=("V2Sig",)):
        path = self.directory / "backfill.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(B15B.SCHEMA)
        for signature in signatures:
            connection.execute(
                "INSERT OR REPLACE INTO t0_state(signature,slot,trade_count_in_launch_tx,"
                "provenance,missing_fields,evidence_sha256,quote_mint) "
                "VALUES (?,?,1,'p','[]','e','q')", (signature, ACTIVATION + 10))
            connection.execute(
                "INSERT OR REPLACE INTO backfill(signature,slot,mint,attempts,status,"
                "evidence_sha256,backfilled_at_wall_unix) "
                "VALUES (?,?,?,1,'retrieved','e',0.0)", (signature, ACTIVATION + 10, MINT))
        connection.commit()
        connection.close()
        return path

    def exchanges(self, signatures=("V2Sig",), fee_bps=95):
        path = self.directory / "rpc_exchanges.jsonl"
        with path.open("w") as handle:
            for signature in signatures:
                handle.write(json.dumps({
                    "signature": signature,
                    "response_json_or_error": {"result": {"meta": {"logMessages": [
                        f"{PILOT.PROGRAM_DATA_PREFIX}"
                        f"{base64.b64encode(trade_payload(fee_bps)).decode()}"]}}}}) + "\n")
        return path


class TestActivationBoundary(Temp):
    """The rule that keeps a quarantined cell quarantined."""

    def test_a_launch_after_activation_passes(self):
        self.assertTrue(B15H.assert_after_activation(ACTIVATION + 1, ACTIVATION))

    def test_a_launch_at_the_boundary_is_refused(self):
        with self.assertRaisesRegex(Refused, B15H.H_PRE_ACTIVATION):
            B15H.assert_after_activation(ACTIVATION, ACTIVATION)

    def test_a_launch_before_activation_is_refused(self):
        with self.assertRaisesRegex(Refused, "no path by which a quarantined cell is recovered"):
            B15H.assert_after_activation(ACTIVATION - 1, ACTIVATION)

    def test_a_launch_with_no_slot_is_refused(self):
        with self.assertRaises(Refused):
            B15H.assert_after_activation(None, ACTIVATION)

    def test_the_query_itself_excludes_pre_activation_launches(self):
        """Filtered in SQL, not downstream, so nothing can slip past a later branch."""
        path = self.b15a([("Old", ACTIVATION - 500), ("New", ACTIVATION + 500)])
        rows = B15H.eligible_launches(path, ACTIVATION)
        self.assertEqual(["New"], [r[0] for r in rows])

    def test_the_activation_slot_was_chosen_ahead_of_the_present(self):
        activation = self.document["activation"]
        self.assertGreater(activation["activation_slot"], activation["chosen_at_finalized_slot"])
        self.assertEqual(2000, activation["margin_slots"])

    def test_no_retroactive_recovery_is_stated_absolutely(self):
        recovery = self.document["activation"]["no_retroactive_recovery"]
        self.assertIn("under any evidence, ever", recovery["statement"])
        self.assertIn("D_feed_degraded_at_t0", recovery["includes"])


class TestEpistemicPosition(Temp):
    """The question Codex asked, and the two different answers it has."""

    def test_the_launch_level_answer_is_yes(self):
        answer = self.document["the_epistemic_question"]["answer_launch_level"]
        self.assertTrue(answer.startswith("YES"))
        self.assertIn("self-authenticating", answer)

    def test_the_population_level_answer_is_no(self):
        answer = self.document["the_epistemic_question"]["answer_population_level"]
        self.assertTrue(answer.startswith("NO"))

    def test_missed_launch_incidence_is_forbidden_not_merely_absent(self):
        self.assertIn("estimating missed-launch incidence from this feed",
                      self.document["strictly_forbidden"])
        self.assertIn("independent feed",
                      self.document["still_unmeasured"]["missed_launch_incidence"])

    def test_the_coverage_statement_travels_with_every_result(self):
        self.assertIn("conditioned on OBSERVED launches", B15H.COVERAGE_STATEMENT)


class TestProvenance(Temp):
    def test_a_degraded_launch_is_labelled_after_gap(self):
        self.assertEqual(B15H.PROVENANCE_AFTER_GAP, B15H.provenance_of("X", {"X"}))

    def test_a_clean_launch_is_labelled_continuous(self):
        self.assertEqual(B15H.PROVENANCE_CONTINUOUS, B15H.provenance_of("X", set()))

    def test_provenance_is_read_from_the_feed_time_decision(self):
        path = self.b15a([("Clean", ACTIVATION + 1), ("Dirty", ACTIVATION + 2)],
                         degraded=("Dirty",))
        degraded, census = B15H.launch_provenance(path)
        self.assertEqual({"Dirty"}, degraded)
        self.assertEqual(2, census["launches_observed"])
        self.assertEqual(1, census["launches_observed_after_gap"])

    def test_an_unreadable_feed_is_refused_not_treated_as_clean(self):
        degraded, census = B15H.launch_provenance(self.directory / "absent.sqlite")
        self.assertIsNone(degraded)
        self.assertIsNone(census)
        with self.assertRaisesRegex(Refused, "Unknown is not clean"):
            B15H.assert_feed_readable(None)

    def test_after_gap_provenance_survives_into_the_priced_row(self):
        """It is never rewritten as continuous, which is the whole point of keeping it."""
        counts = self._run_one(degraded=("V2Sig",))
        self.assertGreater(counts["checkpointed"], 0)
        connection = sqlite3.connect(self.work / "prospective_entries.sqlite")
        provenances = {row[0] for row in connection.execute(
            "SELECT DISTINCT provenance FROM entry_cell")}
        connection.close()
        self.assertEqual({B15H.PROVENANCE_AFTER_GAP}, provenances)

    def _run_one(self, degraded=(), data=None, b15b_signatures=("V2Sig",),
                 exchange_signatures=("V2Sig",)):
        b15a = self.b15a([("V2Sig", ACTIVATION + 10)], degraded=degraded)
        b15b = self.b15b(b15b_signatures)
        exchange = self.exchanges(exchange_signatures)
        original = B15H.fee_schedules_from_launch_transactions
        B15H.fee_schedules_from_launch_transactions = (
            lambda signatures, decoder, exchange_path=None:
            original(signatures, decoder, exchange))
        self.addCleanup(lambda: setattr(B15H, "fee_schedules_from_launch_transactions", original))

        def opener(request, **_k):
            body = json.loads(request.data.decode())
            payload = (batch_response(ACTIVATION + 20, body["params"][0], data)
                       if body["method"] == "getMultipleAccounts"
                       else {"result": ACTIVATION + 20})

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        B15H.run(b15a_path=b15a, b15b_path=b15b, work_dir=self.work,
                 url="https://h.invalid/?k=1", opener=opener, sleeper=lambda _s: None,
                 slot_source=lambda: ACTIVATION + 5, ticks=1)
        # Past ALL three targets (t0+1, t0+2, t0+4 = ACTIVATION+11/+12/+14). At +12 only two are
        # due, which is correct behaviour and made the first version of this test expect three.
        return B15H.run(b15a_path=b15a, b15b_path=b15b, work_dir=self.work,
                        url="https://h.invalid/?k=1", opener=opener, sleeper=lambda _s: None,
                        slot_source=lambda: ACTIVATION + 20, ticks=1)


class TestNoV1Mixing(Temp):
    def test_a_v1_marker_is_refused(self):
        for marker in B15H.V1_POPULATION_MARKERS:
            with self.subTest(marker=marker):
                with self.assertRaisesRegex(Refused, B15H.H_V1_MIXING):
                    B15H.assert_not_v1({"reason": marker})

    def test_a_clean_record_passes(self):
        self.assertTrue(B15H.assert_not_v1({"reason": "H_CURVE_COMPLETE"}))

    def test_the_freeze_forbids_mixing_by_name(self):
        self.assertIn("mixing V1 and V2 populations", self.document["strictly_forbidden"])


class TestTargetsAndCheckpoints(Temp):
    def test_the_entry_target_is_t0_plus_delay_with_no_horizon(self):
        self.assertEqual(1004, B15H.entry_target_slot(1000, 4))

    def test_a_target_already_passed_at_scheduling_is_refused_not_repaired(self):
        connection = B15H.open_database(self.work / "c.sqlite")
        self.addCleanup(connection.close)
        scheduled, missed = B15H.schedule_entries(
            connection, [("V2Sig", ACTIVATION + 10, MINT, CURVE)], ACTIVATION + 999,
            set(), self.document)
        self.assertEqual(0, scheduled)
        self.assertEqual(3, missed)
        reasons = {row[0] for row in connection.execute(
            "SELECT DISTINCT reason FROM entry_schedule")}
        self.assertEqual({B15H.H_TARGET_MISSED}, reasons)

    def test_a_future_target_is_scheduled(self):
        connection = B15H.open_database(self.work / "c.sqlite")
        self.addCleanup(connection.close)
        scheduled, missed = B15H.schedule_entries(
            connection, [("V2Sig", ACTIVATION + 10, MINT, CURVE)], ACTIVATION + 5,
            set(), self.document)
        self.assertEqual(3, scheduled)
        self.assertEqual(0, missed)

    def test_a_pre_activation_launch_cannot_be_scheduled(self):
        connection = B15H.open_database(self.work / "c.sqlite")
        self.addCleanup(connection.close)
        with self.assertRaisesRegex(Refused, B15H.H_PRE_ACTIVATION):
            B15H.schedule_entries(connection, [("Old", ACTIVATION - 10, MINT, CURVE)],
                                  ACTIVATION - 20, set(), self.document)

    def test_one_shared_checkpoint_per_launch_delay(self):
        connection = B15H.open_database(self.work / "c.sqlite")
        self.addCleanup(connection.close)
        for _ in range(3):
            B15H.schedule_entries(connection, [("V2Sig", ACTIVATION + 10, MINT, CURVE)],
                                  ACTIVATION + 5, set(), self.document)
        rows = connection.execute(
            "SELECT signature, delay_slots, COUNT(*) FROM entry_schedule GROUP BY 1,2").fetchall()
        for *_identity, count in rows:
            self.assertEqual(1, count)


class TestFeeSchedule(Temp):
    def test_it_comes_from_the_preserved_launch_transaction(self):
        path = self.exchanges(("V2Sig",), fee_bps=42)
        schedules = B15H.fee_schedules_from_launch_transactions({"V2Sig"}, DECODER, path)
        self.assertEqual(42, schedules["V2Sig"]["fee_bps"])
        self.assertEqual(5, schedules["V2Sig"]["creator_fee_bps"])

    def test_an_unknown_signature_has_no_schedule(self):
        path = self.exchanges(("Other",))
        self.assertEqual({}, B15H.fee_schedules_from_launch_transactions({"V2Sig"}, DECODER, path))

    def test_a_missing_exchange_log_yields_nothing_rather_than_a_guess(self):
        self.assertEqual({}, B15H.fee_schedules_from_launch_transactions(
            {"V2Sig"}, DECODER, self.directory / "absent.jsonl"))


class TestEndToEnd(TestProvenance):
    def test_a_v2_launch_prices_three_scenarios_from_one_state(self):
        counts = self._run_one()
        self.assertEqual(3, counts["checkpointed"], "three delays, one checkpoint each")
        self.assertEqual(9, counts["cells_priced"], "three scenarios per checkpoint")
        connection = sqlite3.connect(self.work / "prospective_entries.sqlite")
        costs = {row[0] for row in connection.execute(
            "SELECT DISTINCT execution_cost_lamports FROM entry_cell WHERE state='priced'")}
        connection.close()
        self.assertEqual(3, len(costs), "the three scenarios must cost differently")

    def test_a_complete_curve_is_refused(self):
        counts = self._run_one(data=curve_account(complete=True))
        self.assertEqual(0, counts["checkpointed"])
        self.assertIn(B15H.H_CURVE_COMPLETE, counts["refusals_by_code"])

    def test_a_launch_with_no_matching_transaction_is_refused(self):
        counts = self._run_one(b15b_signatures=())
        self.assertEqual(0, counts["checkpointed"])
        self.assertIn(B15H.H_NO_MATCHING_TRANSACTION, counts["refusals_by_code"])

    def test_an_incomplete_t0_state_is_refused(self):
        """B15b recorded the transaction but its t0 state is missing a field."""
        b15a = self.b15a([("V2Sig", ACTIVATION + 10)])
        path = self.directory / "backfill.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(B15B.SCHEMA)
        connection.execute(
            "INSERT OR REPLACE INTO t0_state(signature,slot,trade_count_in_launch_tx,provenance,"
            "missing_fields,evidence_sha256) VALUES (?,?,1,'p','[\"real_quote\"]','e')",
            ("V2Sig", ACTIVATION + 10))
        connection.execute(
            "INSERT OR REPLACE INTO backfill(signature,slot,mint,attempts,status,evidence_sha256,"
            "backfilled_at_wall_unix) VALUES (?,?,?,1,'retrieved','e',0.0)",
            ("V2Sig", ACTIVATION + 10, MINT))
        connection.commit()
        connection.close()
        counts = self._drive(b15a, path)
        self.assertEqual(0, counts["checkpointed"])
        self.assertIn(B15H.H_INCOMPLETE_T0, counts["refusals_by_code"])

    def test_a_failed_batch_refuses_with_no_checkpoint(self):
        b15a = self.b15a([("V2Sig", ACTIVATION + 10)])
        b15b = self.b15b()

        def opener(request, **_k):
            body = json.loads(request.data.decode())
            if body["method"] == "getMultipleAccounts":
                raise TimeoutError("timed out")
            payload = {"result": ACTIVATION + 20}

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        B15H.run(b15a_path=b15a, b15b_path=b15b, work_dir=self.work,
                 url="https://h.invalid/?k=1", opener=opener, sleeper=lambda _s: None,
                 slot_source=lambda: ACTIVATION + 5, ticks=1)
        counts = B15H.run(b15a_path=b15a, b15b_path=b15b, work_dir=self.work,
                          url="https://h.invalid/?k=1", opener=opener, sleeper=lambda _s: None,
                          slot_source=lambda: ACTIVATION + 20, ticks=1)
        self.assertEqual(0, counts["checkpointed"])
        self.assertIn(B15H.H_NO_CHECKPOINT, counts["refusals_by_code"])

    def _drive(self, b15a, b15b):
        exchange = self.exchanges()
        original = B15H.fee_schedules_from_launch_transactions
        B15H.fee_schedules_from_launch_transactions = (
            lambda signatures, decoder, exchange_path=None: original(signatures, decoder,
                                                                     exchange))
        self.addCleanup(lambda: setattr(B15H, "fee_schedules_from_launch_transactions", original))

        def opener(request, **_k):
            body = json.loads(request.data.decode())
            payload = (batch_response(ACTIVATION + 20, body["params"][0])
                       if body["method"] == "getMultipleAccounts"
                       else {"result": ACTIVATION + 20})

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        B15H.run(b15a_path=b15a, b15b_path=b15b, work_dir=self.work,
                 url="https://h.invalid/?k=1", opener=opener, sleeper=lambda _s: None,
                 slot_source=lambda: ACTIVATION + 5, ticks=1)
        return B15H.run(b15a_path=b15a, b15b_path=b15b, work_dir=self.work,
                        url="https://h.invalid/?k=1", opener=opener, sleeper=lambda _s: None,
                        slot_source=lambda: ACTIVATION + 20, ticks=1)

    def test_the_coverage_census_is_returned_with_the_counts(self):
        counts = self._run_one()
        self.assertIsNotNone(counts["coverage_census"])
        self.assertIn("conditioned on OBSERVED launches", counts["coverage_statement"])

    def test_the_run_is_idempotent(self):
        self._run_one()
        connection = sqlite3.connect(self.work / "prospective_entries.sqlite")
        before = connection.execute("SELECT COUNT(*) FROM entry_cell").fetchone()[0]
        connection.close()
        self._run_one()
        connection = sqlite3.connect(self.work / "prospective_entries.sqlite")
        after = connection.execute("SELECT COUNT(*) FROM entry_cell").fetchone()[0]
        connection.close()
        self.assertEqual(before, after)

    def test_the_status_line_carries_the_census_beside_the_counts(self):
        self._run_one()
        report = B15H.status(db_path=self.work / "prospective_entries.sqlite",
                             b15a_path=self.directory / "shadow.sqlite")
        PILOT.assert_redacted(report)
        self.assertEqual(B15H.LABEL, report["label"])
        self.assertFalse(report["executable"])
        self.assertTrue(report["no_retroactive_recovery"])
        self.assertTrue(report["never_mixed_with_v1"])
        self.assertTrue(report["figures_withheld_until_v2_slices_close"])
        self.assertIn("not estimable", report["missed_launch_incidence"])
        self.assertIsNotNone(report["coverage_census"])


class TestGates(Temp):
    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a different boundary"):
            B15H.verify_preregistration(expected_sha256="0" * 64)

    def test_no_execution_surface(self):
        self.assertTrue(B15H.assert_no_execution_surface())

    def test_a_planted_execution_surface_is_caught(self):
        for token in ("sendTransaction", "simulateTransaction", "Keypair"):
            with self.subTest(token=token):
                planted = self.directory / f"p_{token}.py"
                planted.write_text(f"x = {token}\n")
                with self.assertRaises(Refused):
                    B15H.assert_no_execution_surface(planted)

    def test_writing_into_upstream_evidence_is_refused(self):
        for marker in ("b15a", "b15b", "b15d", "b15f", "b15g", "b11a"):
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    B15H.assert_isolated(ROOT / "research" / marker / "b15h")

    def test_a_directory_that_is_not_b15h_is_refused(self):
        with self.assertRaisesRegex(Refused, "must be .../b15h"):
            B15H.assert_isolated(self.directory / "elsewhere")

    def test_the_real_work_dir_passes(self):
        self.assertTrue(B15H.assert_isolated(B15H.WORK_DIR))

    def test_a_float_is_refused_as_this_modules_own_refusal(self):
        with self.assertRaises(Refused):
            B15H.assert_no_float({"total_outlay_lamports": 1.5})


if __name__ == "__main__":
    unittest.main()
