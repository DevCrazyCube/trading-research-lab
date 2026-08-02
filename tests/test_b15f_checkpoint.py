"""B15f — the checkpoint guards, each shown to be able to refuse.

The dangerous failures here are all forms of pretending: a past target filled with present state, a
late response used as if it were on time, an account parsed on the assumption its layout is
probably right, or a target scheduled twice or dropped by a restart. Every test below breaks one of
those, and the scheduling ones run against a synthetic slot clock so a future target can be watched
crossing its own deadline.
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


B15F = _load("b15f_checkpoint", "b15f_checkpoint.py")
B15E, B15D, B15B, PILOT, B10A = B15F.B15E, B15F.B15D, B15F.B15B, B15F.PILOT, B15F.B10A
Refused = B15F.CheckpointRefused

MINT = "1thX6LZfHDZZbBQTG5s2XkvGXqivXhSpqSGuKAM1oV5"
CURVE = "So11111111111111111111111111111111111111112"
DECODER = B15B.build_decoder()


def curve_account(virtual_quote=31_000_000_000, virtual_token=1_000_000_000_000,
                  real_quote=1_000_000_000, real_token=700_000_000_000, complete=False,
                  mayhem=False, discriminator=None):
    """A BondingCurve account built from the PINNED layout, so the fixture cannot drift."""
    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
    types = DECODER["types"]
    overrides = {"virtual_token_reserves": virtual_token,
                 "virtual_quote_reserves": virtual_quote,
                 "real_token_reserves": real_token, "real_quote_reserves": real_quote,
                 "token_total_supply": 1_000_000_000_000_000, "complete": complete,
                 "creator": MINT, "is_mayhem_mode": mayhem, "is_cashback_coin": False,
                 "quote_mint": b9d.NATIVE_QUOTE_MINT}
    body = bytearray(discriminator if discriminator is not None
                     else B15F.BONDING_CURVE_DISCRIMINATOR)
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


def account_response(context_slot, data=None, owner=None, lamports=1_000_000, value=True):
    payload = {"result": {"context": {"slot": context_slot}, "value": None}}
    if value:
        payload["result"]["value"] = {
            "owner": owner if owner is not None else B15F.PUMP_PROGRAM,
            "lamports": lamports,
            "data": [base64.b64encode(data if data is not None else curve_account()).decode(),
                     "base64"]}
    return payload


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15f-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15f"
        self.work.mkdir()
        self.document = B15F.verify_preregistration()

    def b15a(self, launches):
        path = self.directory / "shadow.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(PILOT.SCHEMA)
        for index, (signature, slot) in enumerate(launches, start=1):
            connection.execute(
                "INSERT OR IGNORE INTO launch(launch_seq,session_id,frame_seq,signature,slot,mint,"
                "bonding_curve,decoded_wall_unix,decoded_monotonic_ns,decode_status,"
                "evidence_sha256,create_key) VALUES (?,?,?,?,?,?,?,0.0,0,?,'e',?)",
                (index, "s", index, signature, slot, MINT, CURVE, PILOT.DECODE_DECODED,
                 f"k{index}"))
        connection.commit()
        connection.close()
        return path


class TestProspectiveOnly(Temp):
    """The rule that separates this from a retrospective repair."""

    def test_a_future_target_is_schedulable(self):
        self.assertTrue(B15F.is_schedulable(2000, 1000))

    def test_a_target_that_has_already_passed_is_not(self):
        self.assertFalse(B15F.is_schedulable(1000, 2000))

    def test_the_boundary_is_strict(self):
        """A target equal to the current slot has already been reached; it is not future."""
        self.assertFalse(B15F.is_schedulable(1500, 1500))

    def test_the_target_formula_is_nominal_and_documented_as_such(self):
        self.assertEqual(1000 + 2 + 1000, B15F.target_slot(1000, 2, 1000))
        self.assertTrue(self.document["scheduling"]["target_is_NOMINAL"]["statement"])
        self.assertIn("NEVER mixed",
                      self.document["scheduling"]["target_is_NOMINAL"]["consequence"])

    def test_past_targets_are_recorded_with_their_own_reason(self):
        connection = B15F.open_database(self.work / "c.sqlite")
        self.addCleanup(connection.close)
        # t0 far in the past: every target has gone.
        scheduled, skipped = B15F.schedule_new(
            connection, [("OldSig", 1000, MINT, CURVE)], 999_999, self.document)
        self.assertEqual(0, scheduled)
        self.assertEqual(6, skipped, "3 delays x 2 schedulable horizons")
        states = dict(connection.execute("SELECT state, COUNT(*) FROM schedule GROUP BY 1"))
        self.assertEqual({B15F.STATE_NOT_SCHEDULED: 6}, states)
        reason = connection.execute("SELECT DISTINCT reason FROM schedule").fetchone()[0]
        self.assertEqual(B15F.C_PRE_CHECKPOINT_PROTOCOL, reason)

    def test_only_slot_addressable_horizons_are_scheduled(self):
        connection = B15F.open_database(self.work / "c.sqlite")
        self.addCleanup(connection.close)
        B15F.schedule_new(connection, [("S", 1000, MINT, CURVE)], 500, self.document)
        horizons = {row[0] for row in connection.execute("SELECT DISTINCT horizon FROM schedule")}
        self.assertEqual({"h_1000_slots", "h_10000_slots"}, horizons)
        self.assertNotIn("h_10_observations", horizons)


class TestSyntheticClockScheduling(Temp):
    """A future target watched crossing its own deadline, on a clock this test controls."""

    def _clock(self, slots):
        state = {"index": 0}

        def read():
            value = slots[min(state["index"], len(slots) - 1)]
            state["index"] += 1
            return value
        return read

    def _opener(self, context_slot, data=None):
        def opener(request, **_k):
            payload = account_response(context_slot, data)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()
        return opener

    def test_a_target_is_scheduled_before_it_passes_then_fired_after(self):
        b15a = self.b15a([("FutureSig", 10_000)])
        # Tick one at slot 9,000: target 10,000+1+1,000 = 11,001 is still in the future.
        first = B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                         opener=self._opener(11_050), sleeper=lambda _s: None,
                         slot_source=self._clock([9_000]), ticks=1)
        self.assertEqual(6, first["scheduled"])
        self.assertEqual(0, first["due"], "nothing is due before its target")
        self.assertEqual(0, first["checkpointed"])
        # Tick two at slot 11,100: the h_1000 targets are now due.
        second = B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                          opener=self._opener(11_050), sleeper=lambda _s: None,
                          slot_source=self._clock([11_100]), ticks=1)
        self.assertEqual(0, second["scheduled"], "already scheduled; not scheduled twice")
        self.assertGreater(second["due"], 0)
        self.assertGreater(second["checkpointed"], 0)

    def test_a_restart_neither_duplicates_nor_drops_a_pending_target(self):
        b15a = self.b15a([("FutureSig", 10_000)])
        B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                 opener=self._opener(11_050), sleeper=lambda _s: None,
                 slot_source=self._clock([9_000]), ticks=1)
        connection = sqlite3.connect(self.work / "checkpoints.sqlite")
        before = connection.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
        pending = connection.execute(
            "SELECT COUNT(*) FROM schedule WHERE state=?", (B15F.STATE_SCHEDULED,)).fetchone()[0]
        connection.close()
        # "Restart": a brand new process reads the durable schedule, not memory.
        B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                 opener=self._opener(11_050), sleeper=lambda _s: None,
                 slot_source=self._clock([9_050]), ticks=1)
        connection = sqlite3.connect(self.work / "checkpoints.sqlite")
        after = connection.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
        still_pending = connection.execute(
            "SELECT COUNT(*) FROM schedule WHERE state=?", (B15F.STATE_SCHEDULED,)).fetchone()[0]
        connection.close()
        self.assertEqual(before, after, "a restart must not duplicate a schedule row")
        self.assertEqual(pending, still_pending, "a pending target is still due after a restart")

    def test_one_checkpoint_per_identity_even_across_ticks(self):
        b15a = self.b15a([("FutureSig", 10_000)])
        for _ in range(3):
            B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                     opener=self._opener(11_050), sleeper=lambda _s: None,
                     slot_source=self._clock([11_100]), ticks=1)
        connection = sqlite3.connect(self.work / "checkpoints.sqlite")
        rows = connection.execute(
            "SELECT entry_signature, delay_slots, horizon, COUNT(*) FROM checkpoint "
            "GROUP BY 1,2,3").fetchall()
        connection.close()
        for *_identity, count in rows:
            self.assertEqual(1, count, "one checkpoint per entry/scenario/horizon")

    def test_the_raw_log_is_never_opened(self):
        source = (ROOT / "scripts" / "b15f_checkpoint.py").read_text()
        self.assertNotIn("raw_frames.jsonl", source)


class TestContextSlotGeometry(Temp):
    def test_a_context_at_the_target_is_admissible(self):
        self.assertEqual(0, B15F.assert_geometry(11_000, 11_000, self.document))

    def test_a_context_within_the_tolerance_is_admissible(self):
        self.assertEqual(150, B15F.assert_geometry(11_150, 11_000, self.document))

    def test_a_context_one_slot_beyond_the_tolerance_is_refused(self):
        with self.assertRaisesRegex(Refused, B15F.C_LATE):
            B15F.assert_geometry(11_151, 11_000, self.document)

    def test_a_context_before_the_target_is_early_not_late(self):
        with self.assertRaisesRegex(Refused, B15F.C_EARLY_EXHAUSTED):
            B15F.assert_geometry(10_999, 11_000, self.document)

    def test_a_missing_context_is_refused(self):
        with self.assertRaisesRegex(Refused, B15F.C_RPC_EXHAUSTED):
            B15F.assert_geometry(None, 11_000, self.document)

    def test_the_tolerance_is_the_frozen_one(self):
        self.assertEqual(150, self.document["context_slot_geometry"]["max_lateness_slots"])
        self.assertIn("widening max_lateness_slots after seeing a result",
                      self.document["strictly_forbidden"])


class TestAccountDecoding(Temp):
    def test_the_pinned_layout_decodes(self):
        fields = B15F.decode_bonding_curve(curve_account(), DECODER)
        self.assertEqual(31_000_000_000, fields["virtual_quote_reserves"])
        self.assertFalse(fields["complete"])

    def test_a_wrong_discriminator_is_refused_not_parsed(self):
        data = curve_account(discriminator=bytes(8))
        with self.assertRaisesRegex(Refused, B15F.C_SCHEMA):
            B15F.decode_bonding_curve(data, DECODER)

    def test_data_shorter_than_a_discriminator_is_refused(self):
        with self.assertRaisesRegex(Refused, B15F.C_SCHEMA):
            B15F.decode_bonding_curve(b"\x17\xb7", DECODER)

    def test_truncated_data_is_a_decode_refusal(self):
        with self.assertRaisesRegex(Refused, B15F.C_DECODE):
            B15F.decode_bonding_curve(B15F.BONDING_CURVE_DISCRIMINATOR + b"\x00" * 4, DECODER)

    def test_the_account_supplies_real_quote_and_complete(self):
        """The two fields the log feed structurally cannot give, which is why this exists."""
        fields = B15F.decode_bonding_curve(curve_account(real_quote=4242, complete=True), DECODER)
        state = B15F.state_from_account(fields, 11_000)
        self.assertEqual(4242, state["real_quote"])
        self.assertTrue(state["complete"])

    def test_a_state_missing_a_field_is_refused_not_defaulted(self):
        """Called with fields the layout did not fill; absence is not zero."""
        with self.assertRaisesRegex(Refused, B15F.C_DECODE):
            B15F.state_from_account({"virtual_quote_reserves": 1}, 11_000)

    def test_an_account_with_empty_data_is_refused(self):
        payload = account_response(11_000)
        payload["result"]["value"]["data"] = []
        with self.assertRaisesRegex(Refused, B15F.C_ACCOUNT_CLOSED):
            B15F.read_account(payload, 11_000, self.document, DECODER)

    def test_a_missing_owner_is_refused(self):
        with self.assertRaisesRegex(Refused, B15F.C_WRONG_OWNER):
            B15F.read_account(account_response(11_000, owner="SomeoneElse"), 11_000,
                              self.document, DECODER)

    def test_a_null_account_is_refused(self):
        with self.assertRaisesRegex(Refused, B15F.C_ACCOUNT_MISSING):
            B15F.read_account(account_response(11_000, value=False), 11_000, self.document,
                              DECODER)

    def test_a_closed_account_is_refused(self):
        with self.assertRaisesRegex(Refused, B15F.C_ACCOUNT_CLOSED):
            B15F.read_account(account_response(11_000, lamports=0), 11_000, self.document,
                              DECODER)

    def test_a_good_account_reads_through(self):
        state, context, lateness = B15F.read_account(
            account_response(11_010), 11_000, self.document, DECODER)
        self.assertEqual(11_010, context)
        self.assertEqual(10, lateness)
        self.assertEqual(11_000, state["slot"], "the state is recorded at the TARGET slot")


class TestTransportFailures(Temp):
    def _throwing(self, *_a, **_k):
        raise TimeoutError("timed out")

    def test_a_failing_getslot_is_refused_visibly(self):
        with self.assertRaisesRegex(Refused, B15F.C_RPC_EXHAUSTED):
            B15F.current_slot("https://h.invalid/?k=1", self._throwing)

    def test_a_failing_account_fetch_refuses_the_due_target(self):
        """Scheduled first while future, then the fetch fails when it comes due."""
        b15a = self.b15a([("FutureSig", 10_000)])

        def working(request, **_k):
            payload = account_response(11_050)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                 opener=working, sleeper=lambda _s: None, slot_source=lambda: 9_000, ticks=1)
        counts = B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                          opener=self._throwing, sleeper=lambda _s: None,
                          slot_source=lambda: 11_100, ticks=1)
        self.assertGreater(counts["refused"], 0)
        self.assertIn(B15F.C_RPC_EXHAUSTED, counts["refusals_by_code"])
        self.assertEqual(0, counts["checkpointed"])


class TestSharedStateSeparateCosts(Temp):
    def test_one_query_serves_all_three_scenarios(self):
        """The chain does not know about our cost scenarios."""
        self.assertIn("ONE getAccountInfo per (launch, delay, horizon)",
                      self.document["one_query_per_shared_state"]["rule"])

    def test_three_exits_are_priced_from_one_checkpoint(self):
        b15a = self.b15a([("FutureSig", 10_000)])

        def opener(request, **_k):
            payload = account_response(11_050)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        # Two ticks on purpose: schedule while the target is still future, fire once it is due.
        # Doing both at 11,100 would find every h_1000 target already passed and fetch nothing.
        B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1", opener=opener,
                 sleeper=lambda _s: None, slot_source=lambda: 9_000, ticks=1)
        B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1", opener=opener,
                 sleeper=lambda _s: None, slot_source=lambda: 11_100, ticks=1)
        connection = sqlite3.connect(self.work / "checkpoints.sqlite")
        per_checkpoint = connection.execute(
            "SELECT entry_signature, delay_slots, horizon, COUNT(*) FROM checkpoint_exit "
            "GROUP BY 1,2,3").fetchall()
        connection.close()
        self.assertTrue(per_checkpoint)
        for *_identity, count in per_checkpoint:
            self.assertEqual(3, count, "three scenarios from one shared state")


class TestGates(Temp):
    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a different protocol"):
            B15F.verify_preregistration(expected_sha256="0" * 64)

    def test_no_execution_surface(self):
        self.assertTrue(B15F.assert_no_execution_surface())

    def test_a_planted_execution_surface_is_caught(self):
        for token in ("sendTransaction", "simulateTransaction", "Keypair", "PRIVATE_KEY"):
            with self.subTest(token=token):
                planted = self.directory / f"p_{token}.py"
                planted.write_text(f"x = {token}\n")
                with self.assertRaises(Refused):
                    B15F.assert_no_execution_surface(planted)

    def test_writing_into_upstream_evidence_is_refused(self):
        for marker in ("b15a", "b15b", "b15c", "b15d", "b15e", "b11a"):
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    B15F.assert_isolated(ROOT / "research" / marker / "b15f")

    def test_a_directory_that_is_not_b15f_is_refused(self):
        with self.assertRaisesRegex(Refused, "must be .../b15f"):
            B15F.assert_isolated(self.directory / "elsewhere")

    def test_the_real_work_dir_passes(self):
        self.assertTrue(B15F.assert_isolated(B15F.WORK_DIR))

    def test_a_float_is_refused_as_this_modules_own_refusal(self):
        with self.assertRaises(Refused):
            B15F.assert_no_float({"real_quote": 1.5})

    def test_no_credential_reaches_the_exchange_log(self):
        b15a = self.b15a([("FutureSig", 10_000)])

        def opener(request, **_k):
            payload = account_response(11_050)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        for slot in (9_000, 11_100):
            B15F.run(b15a_path=b15a, work_dir=self.work,
                     url="https://h.invalid/path?api-key=SUPERSECRET", opener=opener,
                     sleeper=lambda _s: None, slot_source=lambda slot=slot: slot, ticks=1)
        blob = (self.work / "rpc_exchanges.jsonl").read_text()
        self.assertNotIn("SUPERSECRET", blob)
        self.assertIn("https://h.invalid", blob)

    def test_the_status_line_is_redacted_and_labelled(self):
        b15a = self.b15a([("FutureSig", 10_000)])
        B15F.run(b15a_path=b15a, work_dir=self.work, url="https://h.invalid/?k=1",
                 opener=lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timed out")),
                 sleeper=lambda _s: None, slot_source=lambda: 9_000, ticks=1)
        report = B15F.status(db_path=self.work / "checkpoints.sqlite")
        PILOT.assert_redacted(report)
        self.assertEqual(B15F.LABEL, report["label"])
        self.assertFalse(report["executable"])
        self.assertTrue(report["no_retrospective_mix_with_b15e"])
        self.assertTrue(report["already_passed_targets_stay_censored"])
        self.assertEqual("unmeasured", report["market_impact"])


if __name__ == "__main__":
    unittest.main()
