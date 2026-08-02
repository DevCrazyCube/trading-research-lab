"""B15d — the route and pricing guards, each shown to be able to refuse.

The failures that matter here are substitutions that look like answers: a later snapshot standing
in for the delayed state, a total fee fed where a priority fee belongs, an unavailable component
priced as zero, a duplicated frame counted twice, or a candidate quietly dropped because it could
not be priced. Every test below breaks one of those.
"""
import base64
import copy
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


B15D = _load("b15d_shadow_entry", "b15d_shadow_entry.py")
B15C = B15D.B15C
B15B = B15D.B15B
PILOT = B15D.PILOT
B10A = B15D.B10A
Refused = B15D.ShadowEntryRefused

MINT = "1thX6LZfHDZZbBQTG5s2XkvGXqivXhSpqSGuKAM1oV5"
DECODER = B15B.build_decoder()
TRADE = next(bytes(e["discriminator"]).hex()
             for e in json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
             ["events"] if e["name"] == "TradeEvent")


def trade_payload(virtual_quote=31_000_000_000, virtual_token=1_000_000_000_000,
                  real_quote=1_000_000_000, real_token=700_000_000_000, mint=MINT,
                  fee_bps=95, creator_bps=5, cashback_bps=0, buyback_bps=0, mayhem=False):
    types = DECODER["types"]
    discriminator = bytes(next(e["discriminator"] for e in json.loads(
        (ROOT / "research" / "pump_idl_9c82f61.json").read_text())["events"]
        if e["name"] == "TradeEvent"))
    overrides = {"mint": mint, "is_buy": True, "virtual_quote_reserves": virtual_quote,
                 "virtual_sol_reserves": virtual_quote, "virtual_token_reserves": virtual_token,
                 "real_quote_reserves": real_quote, "real_sol_reserves": real_quote,
                 "real_token_reserves": real_token, "fee_basis_points": fee_bps,
                 "creator_fee_basis_points": creator_bps,
                 "cashback_fee_basis_points": cashback_bps,
                 "buyback_fee_basis_points": buyback_bps, "mayhem_mode": mayhem,
                 "quote_mint": _native_quote_mint()}
    body = bytearray(discriminator)
    for field in types["TradeEvent"]["type"]["fields"]:
        body += _encode(field, types, overrides)
    return bytes(body)


def _native_quote_mint():
    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    return b9d.NATIVE_QUOTE_MINT


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


def frame(signature, slot, payload=None, err=None):
    payload = trade_payload() if payload is None else payload
    return {"frame_seq": slot, "session_id": "s", "received_wall_unix": 0.0,
            "received_monotonic_ns": 0, "commitment": "confirmed",
            "raw_notification_json": {"params": {"result": {
                "context": {"slot": slot},
                "value": {"signature": signature, "err": err,
                          "logs": [f"{PILOT.PROGRAM_DATA_PREFIX}"
                                   f"{base64.b64encode(payload).decode()}"]}}}}}


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15d-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15d"
        self.work.mkdir()
        self.document = B15D.verify_preregistration()

    def raw(self, frames):
        path = self.directory / "raw.jsonl"
        with path.open("w") as handle:
            for item in frames:
                handle.write(json.dumps(item) + "\n")
        return path

    def b15b(self, rows=((("LaunchSig", 1000, MINT)),)):
        path = self.directory / "backfill.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(B15B.SCHEMA)
        for signature, slot, mint in rows:
            connection.execute(
                "INSERT OR IGNORE INTO t0_state(signature,slot,trade_count_in_launch_tx,provenance,"
                "missing_fields,evidence_sha256) VALUES (?,?,1,'p','[]','e')",
                (signature, slot))
            # The token mint lives on `backfill`; t0_state's quote_mint is the SOL sentinel.
            connection.execute(
                "INSERT OR IGNORE INTO backfill(signature,slot,mint,attempts,status,evidence_sha256,"
                "backfilled_at_wall_unix) VALUES (?,?,?,1,'retrieved','e',0.0)",
                (signature, slot, mint))
        connection.commit()
        connection.close()
        return path


class TestRouteDefinition(Temp):
    def test_the_route_sends_no_tips_and_says_that_is_a_choice(self):
        route = self.document["route"]
        self.assertEqual(0, route["tip_lamports"])
        self.assertTrue(route["operator_decision"])
        self.assertEqual([], route["tip_is_an_operator_route_choice_not_an_inference"]
                         ["tip_account_set"])

    def test_zero_tip_here_is_a_route_choice_not_the_unavailable_of_b15c(self):
        """The distinction the whole freeze turns on.

        B15c recorded tip as UNAVAILABLE because no tip-account set was declared. Here the zero is
        legitimate for the opposite reason: nothing would be sent, so there is nothing to observe.
        """
        context = json.loads((ROOT / "research" / "B15C_COST_CONTEXT.json").read_text())
        self.assertFalse(context["components_available"]["tip"])
        self.assertEqual(0, self.document["route"]["tip_lamports"])
        statement = self.document["route"][
            "tip_is_an_operator_route_choice_not_an_inference"]["statement"]
        self.assertIn("DOES NOT SEND TIPS", statement)

    def test_no_landing_probability_is_claimed_anywhere(self):
        text = json.dumps(self.document).lower()
        self.assertIn("no scenario here estimates a landing probability",
                      self.document["route"]["no_landing_guarantee"].lower())
        for banned in ("will_land", "guaranteed", "quoted"):
            self.assertIn(banned, self.document["status_locks"]["refused_status_names"])

    def test_the_route_is_not_executable(self):
        self.assertFalse(self.document["route"]["executable"])
        self.assertFalse(self.document["status_locks"]["executable"])


class TestCostPolicy(Temp):
    def _scenario(self, name):
        return next(s for s in self.document["cost_scenarios"] if s["scenario_id"] == name)

    def test_every_scenario_states_every_required_field(self):
        for scenario in self.document["cost_scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                policy = B15D.cost_policy(scenario)
                self.assertEqual(set(B10A.REQUIRED_POLICY_FIELDS), set(policy))
                B10A.assert_cost_policy(policy)

    def test_a_missing_component_is_refused_not_zeroed(self):
        for field in B10A.REQUIRED_POLICY_FIELDS:
            with self.subTest(field=field):
                scenario = dict(self._scenario("base"))
                scenario.pop(field)
                with self.assertRaisesRegex(Refused, "absence is not zero"):
                    B15D.cost_policy(scenario)

    def test_a_float_cost_is_refused(self):
        scenario = dict(self._scenario("base"), priority_fee_lamports=100000.0)
        with self.assertRaisesRegex(Refused, "exact integer"):
            B15D.cost_policy(scenario)

    def test_ata_rent_comes_from_primary_evidence_and_is_never_refunded(self):
        rent = self.document["ata_rent"]
        self.assertEqual(2039280, rent["lamports"])
        self.assertEqual(165, rent["account_size_bytes"])
        self.assertFalse(rent["refundable"])
        self.assertIn("getMinimumBalanceForRentExemption", rent["source"])

    def test_failed_attempts_are_explicit_per_scenario(self):
        values = {s["scenario_id"]: s["failed_attempts"] for s in self.document["cost_scenarios"]}
        self.assertEqual({"optimistic": 0, "base": 0, "stressed": 1}, values)
        for scenario in self.document["cost_scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                self.assertIn("basis", " ".join(scenario.keys()))
                self.assertTrue(scenario["failed_attempts_basis"])


class TestNoDoubleCounting(Temp):
    def setUp(self):
        super().setUp()
        self.context = json.loads((ROOT / "research" / "B15C_COST_CONTEXT.json").read_text())

    def test_the_real_scenarios_use_the_prioritization_distribution(self):
        for scenario in self.document["cost_scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                self.assertTrue(B15D.assert_no_double_count(scenario, self.context))

    def test_feeding_the_total_fee_as_priority_is_refused(self):
        """The trap: both distributions live in one artifact and the wrong one looks plausible."""
        total_only = [v for k, v in self.context["total_fee_lamports"].items()
                      if k.endswith("_lamports") and isinstance(v, int)
                      and v not in {p for pk, p in
                                    self.context["prioritization_fee_lamports"].items()
                                    if pk.endswith("_lamports") and isinstance(p, int)}]
        self.assertTrue(total_only, "the two distributions must differ for this test to bite")
        scenario = dict(self.document["cost_scenarios"][1], priority_fee_lamports=total_only[0])
        with self.assertRaisesRegex(Refused, "charge it twice"):
            B15D.assert_no_double_count(scenario, self.context)

    def test_b10a_sums_base_and_priority_itself(self):
        """Why they must stay separate: the pair is charged again per failed attempt."""
        source = (ROOT / "scripts" / "b10a_simulator_kernel.py").read_text()
        self.assertIn('policy["base_fee_lamports"] + policy["priority_fee_lamports"]', source)

    def test_the_two_distributions_are_not_composable(self):
        """Separate order statistics over different subsets; adding them mixes two samples."""
        totals = self.context["total_fee_lamports"]
        priorities = self.context["prioritization_fee_lamports"]
        self.assertNotEqual(totals["observations"], priorities["observations"])
        self.assertNotEqual(totals["base_p50_lamports"],
                            5000 + priorities["base_p50_lamports"])


class TestDelayBoundary(Temp):
    def _observations(self, slots):
        return B15D.curve_observations(
            self.raw([frame(f"S{slot}", slot) for slot in slots]), MINT, DECODER, TRADE)

    def test_the_first_observation_at_or_after_the_delay_is_chosen(self):
        observations = self._observations([1000, 1001, 1002, 1004])
        _state, observation = B15D.state_at_or_after(observations, 1000, 2)
        self.assertEqual(1002, observation["slot"])

    def test_the_boundary_is_inclusive_at_the_delay(self):
        observations = self._observations([1002])
        _state, observation = B15D.state_at_or_after(observations, 1000, 2)
        self.assertEqual(1002, observation["slot"], "at or after means AT counts")

    def test_an_observation_before_the_delay_is_not_used(self):
        observations = self._observations([1000, 1001])
        state, observation = B15D.state_at_or_after(observations, 1000, 2)
        self.assertIsNone(state)
        self.assertIsNone(observation)

    def test_a_later_observation_never_stands_in_when_none_reaches_the_delay(self):
        """The substitution this function exists to prevent."""
        observations = self._observations([1000])
        state, observation = B15D.state_at_or_after(observations, 1000, 4)
        self.assertIsNone(observation)
        self.assertIsNone(state)

    def test_a_bigger_delay_never_picks_an_earlier_observation(self):
        observations = self._observations([1001, 1002, 1004, 1010])
        previous = 0
        for delay in (1, 2, 4):
            _state, observation = B15D.state_at_or_after(observations, 1000, delay)
            self.assertGreaterEqual(observation["slot"], previous)
            previous = observation["slot"]


class TestCanonicalOrderingAndDuplicates(Temp):
    def test_observations_come_back_in_canonical_order(self):
        path = self.raw([frame("S3", 1003), frame("S1", 1001), frame("S2", 1002)])
        slots = [o["slot"] for o in B15D.curve_observations(path, MINT, DECODER, TRADE)]
        self.assertEqual(sorted(slots), slots)

    def test_a_duplicated_frame_collapses_rather_than_counting_twice(self):
        """A reconnect can redeliver a notification; it must not become a second observation."""
        path = self.raw([frame("S1", 1001), frame("S1", 1001)])
        self.assertEqual(1, len(B15D.curve_observations(path, MINT, DECODER, TRADE)))

    def test_another_curve_is_not_mixed_in(self):
        other = trade_payload(mint="So11111111111111111111111111111111111111112")
        path = self.raw([frame("S1", 1001), frame("S2", 1002, payload=other)])
        observations = B15D.curve_observations(path, MINT, DECODER, TRADE)
        self.assertEqual(1, len(observations))

    def test_a_failed_transaction_is_not_an_observation(self):
        path = self.raw([frame("S1", 1001, err={"X": 1}), frame("S2", 1002)])
        observations = B15D.curve_observations(path, MINT, DECODER, TRADE)
        self.assertEqual([1002], [o["slot"] for o in observations])

    def test_a_partial_final_line_is_skipped(self):
        path = self.raw([frame("S1", 1001)])
        with path.open("a") as handle:
            handle.write('{"frame_seq": 2, "raw_no')
        self.assertEqual(1, len(B15D.curve_observations(path, MINT, DECODER, TRADE)))


class TestFeeSchedule(Temp):
    def test_the_schedule_comes_from_this_curve_s_own_observation(self):
        observations = B15D.curve_observations(
            self.raw([frame("S1", 1001, payload=trade_payload(fee_bps=42, creator_bps=7))]),
            MINT, DECODER, TRADE)
        schedule = B15D.fee_schedule_from(observations[0])
        self.assertEqual(42, schedule["fee_bps"])
        self.assertEqual(7, schedule["creator_fee_bps"])
        B10A.assert_fee_schedule(schedule)

    def test_a_missing_component_is_refused_not_zeroed(self):
        observation = {"fields": {"fee_basis_points": 95}}
        with self.assertRaisesRegex(Refused, "not assumed to be zero"):
            B15D.fee_schedule_from(observation)


class TestPricingEndToEnd(Temp):
    def _run(self, frames, rows=None, **kwargs):
        return B15D.run(raw_path=self.raw(frames),
                        b15b_path=self.b15b(rows or ((("LaunchSig", 1000, MINT)),)),
                        work_dir=self.work, **kwargs)

    def test_every_cell_is_recorded_for_every_launch(self):
        counts = self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004, 1010)])
        self.assertEqual(1, counts["launches"])
        self.assertEqual(9, counts["cells"], "3 scenarios x 3 delays")
        self.assertEqual(9, sum(counts["by_status"].values()))

    def test_a_priced_cell_carries_exact_integer_costs(self):
        self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])
        connection = sqlite3.connect(self.work / "shadow_entries.sqlite")
        row = connection.execute(
            "SELECT tokens_out, execution_cost_lamports, total_outlay_lamports, tip_lamports, "
            "ata_rent_lamports FROM candidate WHERE status='priced' LIMIT 1").fetchone()
        connection.close()
        self.assertIsNotNone(row, "at least one cell should price")
        for value in row:
            self.assertIsInstance(value, int)
        self.assertEqual(0, row[3], "the route sends no tip")
        self.assertEqual(2039280, row[4])

    def test_a_priced_cell_charges_the_scenario_it_was_priced_under(self):
        """The defect this replaced: every priced cell recorded an execution cost of ZERO.

        The code summed `result.get("costs") or {}`; B10a's key is `execution_costs`, so the get
        returned an empty dict and the sum returned 0. Three scenarios costing 2.0, 2.1 and 4.0
        million lamports all reported as free, and nothing was raised — zero by absence, arriving
        through `or {}`.
        """
        self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])
        connection = sqlite3.connect(self.work / "shadow_entries.sqlite")
        rows = dict(connection.execute(
            "SELECT scenario_id, MIN(execution_cost_lamports) FROM candidate "
            "WHERE status='priced' GROUP BY 1"))
        connection.close()
        expected = {}
        for scenario in self.document["cost_scenarios"]:
            expected[scenario["scenario_id"]] = (
                scenario["base_fee_lamports"] + scenario["priority_fee_lamports"]
                + scenario["tip_lamports"] + scenario["ata_rent_lamports"]
                + scenario["failed_attempts"] * (scenario["base_fee_lamports"]
                                                 + scenario["priority_fee_lamports"]))
        self.assertEqual(expected, rows)
        for scenario_id, cost in rows.items():
            with self.subTest(scenario=scenario_id):
                self.assertGreater(cost, 0, "a priced entry is never free")

    def test_the_three_scenarios_cost_differently(self):
        """If they all cost the same, the scenario grid is decoration."""
        self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])
        connection = sqlite3.connect(self.work / "shadow_entries.sqlite")
        costs = {row[0] for row in connection.execute(
            "SELECT DISTINCT execution_cost_lamports FROM candidate WHERE status='priced'")}
        connection.close()
        self.assertEqual(3, len(costs), f"expected three distinct scenario costs, got {costs}")

    def test_the_total_outlay_includes_the_curve_fees(self):
        """B10a's own lamports_out_of_wallet, not quote plus execution, which drops the fees."""
        self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])
        connection = sqlite3.connect(self.work / "shadow_entries.sqlite")
        row = connection.execute(
            "SELECT quote_lamports, execution_cost_lamports, total_outlay_lamports FROM candidate "
            "WHERE status='priced' LIMIT 1").fetchone()
        connection.close()
        self.assertGreater(row[2], row[0] + row[1],
                           "total outlay must exceed quote + execution by the curve fees")

    def test_a_result_without_execution_costs_stops_the_run_rather_than_recording_zero(self):
        """A broken pricing contract is not one bad candidate, it is a bad run.

        Recording it as a `refused` row among thousands would bury it. The whole run stops so the
        contract violation is the thing the operator sees.
        """
        original = B10A.price_entry
        self.addCleanup(lambda: setattr(B10A, "price_entry", original))
        B10A.price_entry = lambda *a, **k: {"tokens_out": 1}
        with self.assertRaisesRegex(Refused, "not\\s+a cost of zero"):
            self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])

    def test_stale_candidates_are_preserved_not_dropped(self):
        """The curves with no later observation are disproportionately the ones that died."""
        counts = self._run([frame("S1", 1000)])
        self.assertEqual(9, sum(counts["by_status"].values()))
        self.assertEqual(9, counts["by_status"].get(B15D.STATUS_STALE))

    def test_a_refusal_is_recorded_with_its_reason(self):
        tiny = trade_payload(real_token=1)
        counts = self._run([frame(f"S{slot}", slot, payload=tiny) for slot in (1001, 1002, 1004)])
        self.assertGreater(counts["by_status"].get(B15D.STATUS_REFUSED, 0), 0)
        connection = sqlite3.connect(self.work / "shadow_entries.sqlite")
        reason = connection.execute(
            "SELECT reason FROM candidate WHERE status='refused' LIMIT 1").fetchone()[0]
        connection.close()
        self.assertTrue(reason)

    def test_a_mayhem_curve_is_refused_by_b10a(self):
        mayhem = trade_payload(mayhem=True)
        counts = self._run([frame(f"S{slot}", slot, payload=mayhem)
                            for slot in (1001, 1002, 1004)])
        self.assertEqual(0, counts["by_status"].get(B15D.STATUS_PRICED, 0))

    def test_the_run_publishes_no_profit_or_exit(self):
        counts = self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])
        self.assertTrue(counts["no_profit_or_exit_published"])
        self.assertTrue(counts["no_landing_probability_claimed"])
        # Scanned over the KEYS that carry figures, not the whole document: the report contains
        # `no_profit_or_exit_published`, and a naive substring scan flags the very field that
        # asserts the absence it is looking for.
        keys = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    keys.add(key)
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(counts)
        metric_shaped = [k for k in keys
                         if any(word in k for word in ("profit", "pnl", "realised", "return",
                                                       "exit"))
                         and not k.startswith("no_")]
        self.assertEqual([], metric_shaped, f"a result-shaped field appeared: {metric_shaped}")

    def test_the_run_is_idempotent(self):
        frames = [frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)]
        first = self._run(frames)
        second = self._run(frames)
        self.assertEqual(first["by_status"], second["by_status"])
        connection = sqlite3.connect(self.work / "shadow_entries.sqlite")
        self.assertEqual(9, connection.execute("SELECT COUNT(*) FROM candidate").fetchone()[0])
        connection.close()

    def test_upstream_evidence_is_never_written(self):
        raw = self.raw([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])
        b15b = self.b15b()
        before = (raw.read_bytes(), b15b.read_bytes())
        B15D.run(raw_path=raw, b15b_path=b15b, work_dir=self.work)
        self.assertEqual(before, (raw.read_bytes(), b15b.read_bytes()))

    def test_the_status_line_is_redacted_and_labelled(self):
        self._run([frame(f"S{slot}", slot) for slot in (1001, 1002, 1004)])
        report = B15D.status(db_path=self.work / "shadow_entries.sqlite")
        PILOT.assert_redacted(report)
        self.assertEqual(B15D.LABEL, report["label"])
        self.assertFalse(report["executable"])
        self.assertTrue(report["tip_is_an_operator_route_choice"])
        self.assertTrue(report["no_landing_probability_claimed"])


class TestGates(Temp):
    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a different route"):
            B15D.verify_preregistration(expected_sha256="0" * 64)

    def test_no_execution_surface(self):
        self.assertTrue(B15D.assert_no_execution_surface())

    def test_a_planted_execution_surface_is_caught(self):
        for token in ("sendTransaction", "simulateTransaction", "Keypair", "PRIVATE_KEY"):
            with self.subTest(token=token):
                planted = self.directory / f"p_{token}.py"
                planted.write_text(f"x = {token}\n")
                with self.assertRaises(Refused):
                    B15D.assert_no_execution_surface(planted)

    def test_writing_into_upstream_evidence_is_refused(self):
        for marker in ("b15a", "b15b", "b15c", "b11a"):
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    B15D.assert_isolated(ROOT / "research" / marker / "b15d")

    def test_a_directory_that_is_not_b15d_is_refused(self):
        with self.assertRaisesRegex(Refused, "must be .../b15d"):
            B15D.assert_isolated(self.directory / "elsewhere")

    def test_the_real_work_dir_passes(self):
        self.assertTrue(B15D.assert_isolated(B15D.WORK_DIR))

    def test_a_float_anywhere_is_refused(self):
        with self.assertRaises(Refused):
            B15D.assert_no_float({"total_outlay_lamports": 1.5})


if __name__ == "__main__":
    unittest.main()
