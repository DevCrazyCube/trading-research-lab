"""B15c — the calibration guards, each shown to be able to refuse.

The dangerous failures here are not arithmetic errors, they are quiet substitutions: a missing
component recorded as zero, a sample biased toward the calmest minutes, a failed transaction
priced as a buy, an interpolated quantile nobody paid, or a float standing where a lamport belongs.
Every test below breaks one of those.
"""
import base64
import hashlib
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


B15C = _load("b15c_cost_calibration", "b15c_cost_calibration.py")
B15B = B15C.B15B
PILOT = B15C.PILOT
B15B_TESTS = _load("t_b15b", "b15b_backfill.py") and None  # keep one module graph
Refused = B15C.CalibrationRefused

MINT = "1thX6LZfHDZZbBQTG5s2XkvGXqivXhSpqSGuKAM1oV5"


def b58(data):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(data, "big")
    out = ""
    while number:
        number, remainder = divmod(number, 58)
        out = alphabet[remainder] + out
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + (out or "1")


def unit_limit_data(limit):
    return b58(bytes([B15C.CB_SET_UNIT_LIMIT]) + limit.to_bytes(4, "little"))


def unit_price_data(price):
    return b58(bytes([B15C.CB_SET_UNIT_PRICE]) + price.to_bytes(8, "little"))


def trade_logs(is_buy=True, fee=50_000, creator_fee=10_000):
    """A TradeEvent built from the pinned IDL so the fixture cannot drift from the decoder."""
    decoder = B15B.build_decoder()
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    discriminator = bytes(next(e["discriminator"] for e in idl["events"]
                               if e["name"] == "TradeEvent"))
    types = decoder["types"]
    overrides = {"mint": MINT, "is_buy": is_buy, "fee": fee, "creator_fee": creator_fee,
                 "fee_basis_points": 95, "creator_fee_basis_points": 5,
                 "cashback": 0, "buyback_fee": 0, "quote_amount": 100_000_000,
                 "sol_amount": 100_000_000}
    body = bytearray(discriminator)
    for field in types["TradeEvent"]["type"]["fields"]:
        body += _encode(field, types, overrides)
    payload = bytes(body)
    return [f"{PILOT.PROGRAM_DATA_PREFIX}{base64.b64encode(payload).decode()}"]


def _encode(field, types, overrides):
    name, kind = field["name"], field["type"]
    if name in overrides:
        value = overrides[name]
        if kind in ("pubkey", "publicKey"):
            b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
            return b7d.b58decode(value)
        if kind == "bool":
            return b"\x01" if value else b"\x00"
        return int(value).to_bytes(8, "little")
    return _zero(kind, types)


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


def response(signature="Sig1", slot=1000, fee=10_000, signatures=1, err=None,
             limit=None, price=None, is_buy=True, extra_instructions=(), units=42_000):
    instructions = []
    if limit is not None:
        instructions.append({"programId": B15C.COMPUTE_BUDGET_PROGRAM,
                             "data": unit_limit_data(limit)})
    if price is not None:
        instructions.append({"programId": B15C.COMPUTE_BUDGET_PROGRAM,
                             "data": unit_price_data(price)})
    instructions.extend(extra_instructions)
    return {"result": {
        "slot": slot,
        "transaction": {"signatures": [signature] * signatures,
                        "message": {"instructions": instructions}},
        "meta": {"err": err, "fee": fee, "computeUnitsConsumed": units,
                 "logMessages": trade_logs(is_buy=is_buy)}}}


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15c-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15c"
        self.work.mkdir()
        self.decoder = B15B.build_decoder()


class TestGates(Temp):
    def test_the_committed_freeze_verifies(self):
        document = B15C.verify_preregistration()
        self.assertEqual("B15C_COST_CALIBRATION_V1", document["preregistration_id"])

    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a different sample"):
            B15C.verify_preregistration(expected_sha256="0" * 64)

    def test_no_execution_surface(self):
        self.assertTrue(B15C.assert_no_execution_surface())

    def test_a_planted_execution_surface_is_caught(self):
        for token in ("sendTransaction", "simulateTransaction", "Keypair"):
            with self.subTest(token=token):
                planted = self.directory / f"p_{token}.py"
                planted.write_text(f"x = {token}\n")
                with self.assertRaises(Refused):
                    B15C.assert_no_execution_surface(planted)

    def test_writing_into_upstream_evidence_is_refused(self):
        for marker in ("b15a", "b15b", "b11a"):
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    B15C.assert_isolated(ROOT / "research" / marker / "b15c")

    def test_a_directory_that_is_not_b15c_is_refused(self):
        """Distinct from the marker check above, which fires on upstream paths before this one."""
        with self.assertRaisesRegex(Refused, "must be .../b15c"):
            B15C.assert_isolated(self.directory / "somewhere_else")

    def test_the_real_work_dir_passes(self):
        self.assertTrue(B15C.assert_isolated(B15C.WORK_DIR))
        self.assertTrue(B15C.assert_isolated(self.work))

    def test_a_float_is_refused_because_a_lamport_is_an_integer(self):
        with self.assertRaisesRegex(Refused, "nobody can reconcile"):
            B15C.assert_no_float({"total_fee_lamports": 5000.5})

    def test_a_nested_float_is_caught(self):
        with self.assertRaises(Refused):
            B15C.assert_no_float({"a": [{"b": 1.0}]})


class TestSampling(Temp):
    def test_the_selector_is_deterministic(self):
        for signature in ("A", "B", "SomeSignature"):
            with self.subTest(signature=signature):
                self.assertEqual(B15C.is_sampled(signature, 8),
                                 B15C.is_sampled(signature, 8))

    def test_the_selector_is_reproducible_from_the_signature_alone(self):
        expected = int(hashlib.sha256(b"b15c:XYZ").hexdigest(), 16) % 8 == 0
        self.assertEqual(expected, B15C.is_sampled("XYZ", 8))

    def test_the_sample_is_not_the_first_n(self):
        """Time-neutral by construction: selection depends on the signature, not arrival order."""
        signatures = [f"sig{i}" for i in range(400)]
        chosen = [s for s in signatures if B15C.is_sampled(s, 8)]
        self.assertGreater(len(chosen), 10)
        first_half = sum(1 for s in chosen if int(s[3:]) < 200)
        # A first-N sample would put every selection in one half. A hash sample spreads.
        self.assertGreater(first_half, 5)
        self.assertLess(first_half, len(chosen) - 5)

    def test_the_sampling_rate_is_about_one_in_the_modulus(self):
        signatures = [f"s{i}" for i in range(8000)]
        chosen = sum(1 for s in signatures if B15C.is_sampled(s, 8))
        self.assertGreater(chosen, 800)
        self.assertLess(chosen, 1200)

    def test_a_different_modulus_selects_a_different_set(self):
        signatures = [f"s{i}" for i in range(500)]
        self.assertNotEqual({s for s in signatures if B15C.is_sampled(s, 8)},
                            {s for s in signatures if B15C.is_sampled(s, 3)})


class TestComputeBudget(Temp):
    def test_limit_and_price_are_read_exactly(self):
        limit, price, present, reason = B15C.compute_budget_settings(
            response(limit=250_000, price=1_000)["result"])
        self.assertEqual(250_000, limit)
        self.assertEqual(1_000, price)
        self.assertTrue(present)
        self.assertIsNone(reason)

    def test_no_compute_budget_instruction_means_provably_no_priority_fee(self):
        """Absence is EVIDENCE here: the fee is defined by those instructions."""
        limit, price, present, _reason = B15C.compute_budget_settings(response()["result"])
        fee, provable, reason = B15C.prioritization_fee(limit, price, present)
        self.assertFalse(present)
        self.assertEqual(0, fee)
        self.assertTrue(provable)
        self.assertEqual("no_compute_budget_instruction", reason)

    def test_an_undecodable_instruction_is_unavailable_not_zero(self):
        """The case that must never share a value with the one above."""
        payload = response()
        payload["result"]["transaction"]["message"]["instructions"] = [
            {"programId": B15C.COMPUTE_BUDGET_PROGRAM, "data": "!!!not-base58!!!"}]
        limit, price, present, reason = B15C.compute_budget_settings(payload["result"])
        self.assertEqual(B15C.C03_COMPUTE_BUDGET_UNDECODABLE, reason)
        fee, provable, _reason = B15C.prioritization_fee(limit, price, present)
        self.assertIsNone(fee)
        self.assertFalse(provable)
        self.assertNotEqual(0, fee, "unavailable and zero must not share a value")

    def test_a_price_with_no_limit_is_unavailable(self):
        limit, price, present, _reason = B15C.compute_budget_settings(
            response(price=1_000)["result"])
        fee, provable, reason = B15C.prioritization_fee(limit, price, present)
        self.assertIsNone(fee)
        self.assertFalse(provable)
        self.assertEqual(B15C.C03_COMPUTE_BUDGET_UNDECODABLE, reason)

    def test_the_prioritization_formula_matches_the_primary_source(self):
        """ceil(price * limit / 1e6), on the REQUESTED limit, per solana.com/docs/core/fees."""
        self.assertEqual(1, B15C.prioritization_fee(1, 1, True)[0])
        self.assertEqual(1, B15C.prioritization_fee(1_000_000, 1, True)[0])
        self.assertEqual(2, B15C.prioritization_fee(1_000_001, 1, True)[0])
        self.assertEqual(250, B15C.prioritization_fee(200_000, 1_250, True)[0])

    def test_the_formula_uses_the_limit_not_the_units_consumed(self):
        payload = response(limit=1_000_000, price=1_000, units=1)
        limit, price, present, _reason = B15C.compute_budget_settings(payload["result"])
        fee, _provable, _reason = B15C.prioritization_fee(limit, price, present)
        self.assertEqual(1_000, fee, "consumed units must not enter the prioritization fee")

    def test_the_ceiling_never_rounds_down(self):
        for price, limit in ((1, 1), (3, 7), (999_999, 1), (1, 999_999)):
            with self.subTest(price=price, limit=limit):
                fee = B15C.prioritization_fee(limit, price, True)[0]
                self.assertGreaterEqual(fee * 1_000_000, price * limit)
                self.assertLess((fee - 1) * 1_000_000, price * limit)


class TestTips(Temp):
    def test_an_undeclared_tip_set_makes_tips_unavailable_not_zero(self):
        tip, provable, reason = B15C.tip_lamports(response()["result"], ())
        self.assertIsNone(tip)
        self.assertFalse(provable)
        self.assertEqual("tip_account_set_not_declared", reason)

    def test_a_declared_set_sums_only_transfers_to_it(self):
        transfers = [
            {"programId": B15C.SYSTEM_PROGRAM,
             "parsed": {"type": "transfer", "info": {"destination": "TipA", "lamports": 7000}}},
            {"programId": B15C.SYSTEM_PROGRAM,
             "parsed": {"type": "transfer", "info": {"destination": "Other", "lamports": 900}}},
        ]
        payload = response(extra_instructions=transfers)
        tip, provable, reason = B15C.tip_lamports(payload["result"], {"TipA"})
        self.assertEqual(7000, tip)
        self.assertTrue(provable)
        self.assertIsNone(reason)

    def test_a_declared_set_with_no_matching_transfer_is_zero_and_provable(self):
        tip, provable, _reason = B15C.tip_lamports(response()["result"], {"TipA"})
        self.assertEqual(0, tip)
        self.assertTrue(provable)


class TestDecomposition(Temp):
    def test_a_full_decomposition_agrees_with_meta_fee(self):
        """The empirical answer to what meta.fee contains, rather than a documented claim."""
        priority = B15C.prioritization_fee(200_000, 1_250, True)[0]
        total = B15C.LAMPORTS_PER_SIGNATURE + priority
        record = B15C.decompose(response(fee=total, limit=200_000, price=1_250), "Sig1", 1000,
                                self.decoder)
        self.assertTrue(record["decomposition_checked"])
        self.assertTrue(record["decomposition_agrees"])
        self.assertEqual(B15C.LAMPORTS_PER_SIGNATURE, record["base_fee_lamports"])

    def test_a_disagreement_is_recorded_not_adjusted(self):
        record = B15C.decompose(response(fee=999_999, limit=200_000, price=1_250), "Sig1", 1000,
                                self.decoder)
        self.assertTrue(record["decomposition_checked"])
        self.assertFalse(record["decomposition_agrees"])
        self.assertEqual(999_999, record["total_fee_lamports"], "the fee must not be adjusted")

    def test_base_fee_scales_with_the_signature_count(self):
        record = B15C.decompose(response(signatures=3, fee=15_000), "Sig1", 1000, self.decoder)
        self.assertEqual(3, record["signature_count"])
        self.assertEqual(15_000, record["base_fee_lamports"])

    def test_pump_fee_fields_are_exact_integers_from_the_event(self):
        record = B15C.decompose(response(), "Sig1", 1000, self.decoder)
        self.assertEqual(50_000, record["pump_protocol_fee_lamports"])
        self.assertEqual(10_000, record["pump_creator_fee_lamports"])
        self.assertEqual(95, record["pump_fee_basis_points"])
        B15C.assert_no_float(record)

    def test_a_failed_transaction_is_refused(self):
        with self.assertRaisesRegex(Refused, B15C.C01_TRANSACTION_FAILED):
            B15C.decompose(response(err={"X": 1}), "Sig1", 1000, self.decoder)

    def test_a_sell_only_transaction_is_refused(self):
        with self.assertRaisesRegex(Refused, B15C.C02_NO_BUY_TRADE_EVENT):
            B15C.decompose(response(is_buy=False), "Sig1", 1000, self.decoder)

    def test_a_signature_mismatch_is_refused(self):
        with self.assertRaisesRegex(Refused, B15C.C07_RESPONSE_INCONSISTENT):
            B15C.decompose(response(signature="Other"), "Sig1", 1000, self.decoder)

    def test_a_slot_mismatch_is_refused(self):
        with self.assertRaisesRegex(Refused, B15C.C07_RESPONSE_INCONSISTENT):
            B15C.decompose(response(slot=7), "Sig1", 1000, self.decoder)

    def test_no_component_is_ever_silently_zero(self):
        record = B15C.decompose(response(), "Sig1", 1000, self.decoder)
        self.assertIsNone(record["tip_lamports"])
        self.assertFalse(record["tip_provable"])
        self.assertIsNone(record["compute_unit_price_micro_lamports"])


class TestOrderStatistics(Temp):
    def test_quantiles_are_exact_observations_never_interpolated(self):
        values = [10, 20, 30, 40]
        for numerator, denominator in ((1, 10), (1, 2), (9, 10)):
            with self.subTest(q=(numerator, denominator)):
                self.assertIn(B15C.order_statistic(values, numerator, denominator), values)

    def test_a_two_point_median_picks_a_real_observation(self):
        """An interpolated median of 10 and 20 would report 15, which nobody paid."""
        self.assertIn(B15C.order_statistic([10, 20], 1, 2), (10, 20))
        self.assertNotEqual(15, B15C.order_statistic([10, 20], 1, 2))

    def test_scenarios_over_nothing_say_so(self):
        result = B15C.scenarios_from([])
        self.assertEqual(0, result["observations"])
        self.assertNotIn("base_p50_lamports", result)

    def test_scenarios_are_labelled_simulated_and_non_executable(self):
        result = B15C.scenarios_from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(B15C.SCENARIO_LABEL, result["label"])
        self.assertFalse(result["executable"])
        self.assertIn("not a quote", result["meaning"])

    def test_the_three_scenarios_are_ordered(self):
        values = list(range(1, 101))
        result = B15C.scenarios_from(values)
        self.assertLessEqual(result["optimistic_p10_lamports"], result["base_p50_lamports"])
        self.assertLessEqual(result["base_p50_lamports"], result["stressed_p90_lamports"])

    def test_scenarios_carry_no_float(self):
        B15C.assert_no_float(B15C.scenarios_from([5000, 6000, 7000]))


class TestPopulation(Temp):
    def _raw(self, records):
        path = self.directory / "raw.jsonl"
        with path.open("w") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        return path

    def _frame(self, signature, is_buy=True, err=None, slot=1000):
        return {"frame_seq": 1, "session_id": "s", "received_wall_unix": 0.0,
                "received_monotonic_ns": 0, "commitment": "confirmed",
                "raw_notification_json": {"params": {"result": {
                    "context": {"slot": slot},
                    "value": {"signature": signature, "err": err,
                              "logs": trade_logs(is_buy=is_buy)}}}}}

    def test_only_successful_buys_are_in_population(self):
        path = self._raw([self._frame("Buy1"), self._frame("Sell1", is_buy=False),
                          self._frame("Failed1", err={"X": 1})])
        signatures = {row["signature"] for row in B15C.population(path, self.decoder)}
        self.assertEqual({"Buy1"}, signatures)

    def test_a_duplicate_signature_appears_once(self):
        path = self._raw([self._frame("Buy1"), self._frame("Buy1")])
        self.assertEqual(1, len(B15C.population(path, self.decoder)))

    def test_a_partial_final_line_is_skipped_not_guessed(self):
        """B15a appends while this reads; a half-written line must not stop the sample."""
        path = self._raw([self._frame("Buy1")])
        with path.open("a") as handle:
            handle.write('{"frame_seq": 2, "raw_notif')
        self.assertEqual(1, len(B15C.population(path, self.decoder)))

    def test_no_future_data_is_read(self):
        """The population comes from recorded frames only, never from a live query."""
        source = (ROOT / "scripts" / "b15c_cost_calibration.py").read_text()
        body = source.split("def population(", 1)[1].split("\ndef ", 1)[0]
        for token in ("getSignatures", "getLatestBlockhash", "getSlot", "urlopen"):
            with self.subTest(token=token):
                self.assertNotIn(token, body)


class TestEndToEnd(Temp):
    def _raw(self):
        path = self.directory / "raw.jsonl"
        records = []
        for index in range(200):
            signature = f"CostSig{index}"
            records.append({
                "frame_seq": index, "session_id": "s", "received_wall_unix": 0.0,
                "received_monotonic_ns": 0, "commitment": "confirmed",
                "raw_notification_json": {"params": {"result": {
                    "context": {"slot": 1000},
                    "value": {"signature": signature, "err": None,
                              "logs": trade_logs()}}}}})
        with path.open("w") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        return path

    def _opener(self, fee_for):
        def opener(request, **_k):
            body = json.loads(request.data.decode())
            signature = body["params"][0]
            payload = response(signature=signature, fee=fee_for(signature),
                               limit=200_000, price=(fee_for(signature) - 5000) * 5)

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

    def test_the_run_samples_decomposes_and_produces_ordered_scenarios(self):
        def fee_for(signature):
            return 5000 + B15C.prioritization_fee(
                200_000, (int(signature[7:]) % 20 + 1) * 5, True)[0]

        def opener(request, **_k):
            body = json.loads(request.data.decode())
            signature = body["params"][0]
            price = (int(signature[7:]) % 20 + 1) * 5
            total = 5000 + B15C.prioritization_fee(200_000, price, True)[0]
            payload = response(signature=signature, fee=total, limit=200_000, price=price)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        counts = B15C.run(raw_path=self._raw(), work_dir=self.work, opener=opener,
                          sleeper=lambda _s: None, url="https://h.invalid/?api-key=SECRET")
        self.assertGreater(counts["included"], 5)
        self.assertEqual(0, counts["excluded"])
        scenarios = counts["scenarios"]
        self.assertLessEqual(scenarios["optimistic_p10_lamports"],
                             scenarios["base_p50_lamports"])
        self.assertLessEqual(scenarios["base_p50_lamports"],
                             scenarios["stressed_p90_lamports"])
        self.assertEqual(B15C.SCENARIO_LABEL, scenarios["label"])

    def test_a_decomposition_mismatch_is_excluded_and_counted(self):
        def opener(request, **_k):
            body = json.loads(request.data.decode())
            payload = response(signature=body["params"][0], fee=123_456,
                               limit=200_000, price=1_000)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        counts = B15C.run(raw_path=self._raw(), work_dir=self.work, opener=opener,
                          sleeper=lambda _s: None, url="https://h.invalid/?k=1")
        self.assertEqual(0, counts["included"])
        self.assertGreater(counts["excluded"], 0)
        self.assertIn(B15C.C05_DECOMPOSITION_MISMATCH, counts["exclusions"])

    def test_every_exclusion_is_counted_by_code(self):
        def opener(*_a, **_k):
            raise TimeoutError("timed out")

        counts = B15C.run(raw_path=self._raw(), work_dir=self.work, opener=opener,
                          sleeper=lambda _s: None, url="https://h.invalid/?k=1")
        self.assertEqual(0, counts["included"])
        self.assertIn(B15C.C04_RPC_EXHAUSTED, counts["exclusions"])
        self.assertEqual(counts["excluded"], sum(counts["exclusions"].values()))

    def test_the_run_is_idempotent(self):
        raw = self._raw()

        def opener(request, **_k):
            body = json.loads(request.data.decode())
            payload = response(signature=body["params"][0], fee=5000)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        first = B15C.run(raw_path=raw, work_dir=self.work, opener=opener,
                         sleeper=lambda _s: None, url="https://h.invalid/?k=1")
        second = B15C.run(raw_path=raw, work_dir=self.work, opener=opener,
                          sleeper=lambda _s: None, url="https://h.invalid/?k=1")
        self.assertGreater(first["fetched"], 0)
        self.assertEqual(0, second["fetched"], "a sampled signature must not be refetched")

    def test_no_credential_reaches_any_artifact(self):
        def opener(request, **_k):
            payload = response(signature=json.loads(request.data.decode())["params"][0], fee=5000)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        B15C.run(raw_path=self._raw(), work_dir=self.work, opener=opener,
                 sleeper=lambda _s: None, url="https://h.invalid/?api-key=SUPERSECRET")
        for path in (self.work / "calibration.sqlite", self.work / "rpc_exchanges.jsonl"):
            with self.subTest(path=path.name):
                self.assertNotIn(b"SUPERSECRET", path.read_bytes())

    def test_the_status_line_is_redacted_and_labelled(self):
        def opener(request, **_k):
            payload = response(signature=json.loads(request.data.decode())["params"][0], fee=5000)

            class Handle:
                status = 200

                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False
            return Handle()

        B15C.run(raw_path=self._raw(), work_dir=self.work, opener=opener,
                 sleeper=lambda _s: None, url="https://h.invalid/?k=1")
        report = B15C.status(db_path=self.work / "calibration.sqlite")
        PILOT.assert_redacted(report)
        self.assertEqual(B15C.SCENARIO_LABEL, report["scenario_label"])
        self.assertTrue(report["reads_only"])
        self.assertEqual(0, report["tip_accounts_declared"])


if __name__ == "__main__":
    unittest.main()
