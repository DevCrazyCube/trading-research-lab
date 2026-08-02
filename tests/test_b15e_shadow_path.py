"""B15e — the path and exit guards, each shown to be able to refuse.

The failures that matter are the ones that produce a number rather than an error: a censored cell
scored as a loss, a horizon off by one, an entry paired with the wrong scenario's exit, a missing
cost summed to zero, a refused entry dropped from the denominator, or an observation from at-or-
before the entry sneaking into the path. Every test below breaks one of those.
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


B15E = _load("b15e_shadow_path", "b15e_shadow_path.py")
B15D = B15E.B15D
B15B = B15E.B15B
PILOT = B15E.PILOT
B10A = B15E.B10A
Refused = B15E.ShadowPathRefused

D15D_TESTS = _load("t15d", "b15d_shadow_entry.py") and None
MINT = "1thX6LZfHDZZbBQTG5s2XkvGXqivXhSpqSGuKAM1oV5"
DECODER = B15B.build_decoder()
TRADE = next(bytes(e["discriminator"]).hex()
             for e in json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
             ["events"] if e["name"] == "TradeEvent")


def trade_payload(virtual_quote=31_000_000_000, virtual_token=1_000_000_000_000,
                  real_quote=1_000_000_000, real_token=700_000_000_000, mint=MINT):
    types = DECODER["types"]
    discriminator = bytes(next(e["discriminator"] for e in json.loads(
        (ROOT / "research" / "pump_idl_9c82f61.json").read_text())["events"]
        if e["name"] == "TradeEvent"))
    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    overrides = {"mint": mint, "is_buy": True, "virtual_quote_reserves": virtual_quote,
                 "virtual_sol_reserves": virtual_quote, "virtual_token_reserves": virtual_token,
                 "real_quote_reserves": real_quote, "real_sol_reserves": real_quote,
                 "real_token_reserves": real_token, "fee_basis_points": 95,
                 "creator_fee_basis_points": 5, "cashback_fee_basis_points": 0,
                 "buyback_fee_basis_points": 0, "mayhem_mode": False,
                 "quote_mint": b9d.NATIVE_QUOTE_MINT}
    body = bytearray(discriminator)
    for field in types["TradeEvent"]["type"]["fields"]:
        body += _encode(field, types, overrides)
    return bytes(body)


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


def frame(signature, slot, payload=None):
    payload = trade_payload() if payload is None else payload
    return {"frame_seq": slot, "session_id": "s", "received_wall_unix": 0.0,
            "received_monotonic_ns": 0, "commitment": "confirmed",
            "raw_notification_json": {"params": {"result": {
                "context": {"slot": slot},
                "value": {"signature": signature, "err": None,
                          "logs": [f"{PILOT.PROGRAM_DATA_PREFIX}"
                                   f"{base64.b64encode(payload).decode()}"]}}}}}


def observation(slot, signature="X", **kwargs):
    payload = trade_payload(**kwargs)
    body = payload[len(PILOT.EVENT_TAG):] if payload.startswith(PILOT.EVENT_TAG) else payload
    fields = DECODER["b7d"].read_struct(
        DECODER["b7d"].Cursor(body[8:]), DECODER["types"]["TradeEvent"], DECODER["types"])
    return {"slot": slot, "signature": signature, "log_index": 0, "fields": fields}


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15e-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15e"
        self.work.mkdir()
        self.document = B15E.verify_preregistration()

    def raw(self, frames):
        path = self.directory / "raw.jsonl"
        with path.open("w") as handle:
            for item in frames:
                handle.write(json.dumps(item) + "\n")
        return path

    def b15d(self, cells):
        path = self.directory / "shadow_entries.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(B15D.SCHEMA)
        for signature, scenario, delay, slot, status, tokens, outlay in cells:
            connection.execute(
                "INSERT OR REPLACE INTO candidate(signature,scenario_id,delay_slots,mint,t0_slot,"
                "observation_slot,status,tokens_out,total_outlay_lamports,evidence_sha256,"
                "priced_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,'e',0.0)",
                (signature, scenario, delay, MINT, slot, slot, status, tokens, outlay))
        connection.commit()
        connection.close()
        return path


class TestHorizonRule(Temp):
    """The rule the freeze names explicitly, because the project holds two of them."""

    def test_the_rule_is_the_exit_rule_not_state_in_force(self):
        rule = self.document["horizon_rule"]
        self.assertIn("EXIT", rule["selection_rule"])
        self.assertIn("THIS_IS_NOT_B10C_STATE_IN_FORCE", rule)
        self.assertIn("not comparable", rule["THIS_IS_NOT_B10C_STATE_IN_FORCE"]["consequence"]
                      .lower().replace("figures produced here are not", "not"))

    def test_first_at_or_after_is_selected(self):
        path = [observation(1500), observation(2000), observation(2500)]
        chosen, reason = B15E.select_exit(path, 1000, "h_1000_slots")
        self.assertIsNone(reason)
        self.assertEqual(2000, chosen["slot"], "first at or after 1000+1000")

    def test_the_boundary_is_inclusive(self):
        path = [observation(2000)]
        chosen, _reason = B15E.select_exit(path, 1000, "h_1000_slots")
        self.assertEqual(2000, chosen["slot"], "exactly at the target counts")

    def test_off_by_one_below_the_target_is_censored(self):
        path = [observation(1999)]
        chosen, reason = B15E.select_exit(path, 1000, "h_1000_slots")
        self.assertIsNone(chosen)
        self.assertEqual(B15E.E01_NO_OBSERVATION, reason)

    def test_the_last_at_or_before_is_never_chosen(self):
        """The B10c rule would pick 1999 here. This one must not."""
        path = [observation(1999), observation(2500)]
        chosen, _reason = B15E.select_exit(path, 1000, "h_1000_slots")
        self.assertEqual(2500, chosen["slot"])

    def test_the_observation_horizon_counts_observations_not_slots(self):
        path = [observation(1000 + i) for i in range(1, 15)]
        chosen, _reason = B15E.select_exit(path, 1000, "h_10_observations")
        self.assertEqual(path[9]["slot"], chosen["slot"], "the tenth observation")

    def test_too_few_observations_is_censored(self):
        path = [observation(1001), observation(1002)]
        chosen, reason = B15E.select_exit(path, 1000, "h_10_observations")
        self.assertIsNone(chosen)
        self.assertEqual(B15E.E01_NO_OBSERVATION, reason)

    def test_the_administrative_end_is_the_last_observation(self):
        path = [observation(1100), observation(1200)]
        chosen, _reason = B15E.select_exit(path, 1000, "administrative_window_end")
        self.assertEqual(1200, chosen["slot"])

    def test_an_unknown_horizon_is_refused(self):
        with self.assertRaisesRegex(Refused, "not a frozen horizon"):
            B15E.select_exit([], 1000, "h_invented")

    def test_the_frozen_identifiers_are_b11bs(self):
        b11b = json.loads(
            (ROOT / "research" / "B11B_BASELINE_EVALUATION_PREREGISTRATION.json").read_text())
        self.assertEqual([h["name"] for h in b11b["horizons"]["set"]],
                         self.document["horizon_rule"]["identifiers"])
        self.assertEqual(b11b["primary_result"]["horizon"]
                         if "horizon" in b11b.get("primary_result", {}) else "h_1000_slots",
                         self.document["horizon_rule"]["primary"])


class TestScenarioPairing(Temp):
    def test_matching_scenarios_pass(self):
        self.assertTrue(B15E.assert_scenarios_not_mixed("base", "base"))

    def test_a_mixed_pair_is_refused(self):
        for entry, exit_ in (("optimistic", "stressed"), ("base", "optimistic"),
                             ("stressed", "base")):
            with self.subTest(pair=(entry, exit_)):
                with self.assertRaisesRegex(Refused, "no coherent world"):
                    B15E.assert_scenarios_not_mixed(entry, exit_)

    def test_the_exit_scenarios_match_the_entry_scenario_ids(self):
        entry = json.loads(
            (ROOT / "research" / "B15D_SHADOW_ROUTE_PREREGISTRATION.json").read_text())
        self.assertEqual([s["scenario_id"] for s in entry["cost_scenarios"]],
                         [s["scenario_id"] for s in self.document["exit_cost_scenarios"]])

    def test_ata_rent_is_zero_on_exit_because_it_was_paid_at_entry(self):
        for scenario in self.document["exit_cost_scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                self.assertEqual(0, scenario["ata_rent_lamports"])
        self.assertIn("already paid", self.document["exit_route"]["ata_rent_excluded_because"])

    def test_the_sell_priority_is_declared_a_caller_stated_assumption(self):
        """B15c sampled BUYS; presenting its quantiles as measured sell costs would be invented."""
        note = self.document["exit_route"]["sell_priority_is_a_caller_stated_assumption"]
        self.assertIn("CALLER-STATED ROUTE ASSUMPTION", note["statement"])
        self.assertIn("BUY", note["why_it_is_not_evidence"])


class TestPathConstruction(Temp):
    def test_no_observation_at_or_before_entry_enters_the_path(self):
        """The no-future-at-entry rule, run backwards: no past-at-entry either."""
        raw = self.raw([frame(f"S{slot}", slot) for slot in (900, 1000, 1100, 1200)])
        index = B15D.observations_by_mint(raw, {MINT}, DECODER, TRADE, {MINT: 0})
        path = [o for o in index[MINT] if o["slot"] > 1000]
        self.assertEqual([1100, 1200], [o["slot"] for o in path])

    def test_a_duplicated_frame_does_not_become_two_observations(self):
        raw = self.raw([frame("S1", 1100), frame("S1", 1100)])
        index = B15D.observations_by_mint(raw, {MINT}, DECODER, TRADE)
        self.assertEqual(1, len(index[MINT]))

    def test_the_path_is_in_canonical_order(self):
        raw = self.raw([frame("S3", 1300), frame("S1", 1100), frame("S2", 1200)])
        index = B15D.observations_by_mint(raw, {MINT}, DECODER, TRADE)
        slots = [o["slot"] for o in index[MINT]]
        self.assertEqual(sorted(slots), slots)


class TestDrawdown(Temp):
    def test_it_is_computed_on_the_path_not_the_endpoints(self):
        """A position that ended flat after losing four fifths is not one that never moved."""
        self.assertEqual(80, B15E.maximum_drawdown([100, 20, 100]))
        self.assertEqual(0, B15E.maximum_drawdown([100, 100, 100]))

    def test_an_empty_path_has_no_drawdown_rather_than_zero(self):
        self.assertIsNone(B15E.maximum_drawdown([]))

    def test_a_monotonic_rise_has_no_drawdown(self):
        self.assertEqual(0, B15E.maximum_drawdown([1, 2, 3, 4]))


class TestEndToEnd(Temp):
    # A position proportionate to the curve it was bought on. The first version held 250 billion
    # tokens against a curve with one SOL of real quote, and B10a rightly refused to price an exit
    # the reserves could not pay — correct behaviour, but it meant no cell ever reached `exited`
    # and the tests that matter never ran.
    TOKENS_HELD = 3_000_000_000

    def _cells(self, status=B15D.STATUS_PRICED):
        return [("EntrySig", scenario, 1, 1000, status, self.TOKENS_HELD, 103_394_280)
                for scenario in ("optimistic", "base", "stressed")]

    def _run(self, frames, cells=None, **kwargs):
        return B15E.run(raw_path=self.raw(frames), b15d_path=self.b15d(cells or self._cells()),
                        work_dir=self.work, **kwargs)

    def test_every_cell_and_horizon_is_recorded(self):
        counts = self._run([frame(f"S{slot}", slot) for slot in (1100, 2100, 3000)])
        self.assertEqual(12, counts["cells"], "3 scenarios x 4 horizons")
        self.assertEqual(12, sum(counts["by_status"].values()))

    def test_a_refused_entry_stays_in_the_denominator(self):
        counts = self._run([frame("S1", 2100)], cells=self._cells(status="refused"))
        self.assertEqual(12, counts["cells"])
        self.assertEqual(12, counts["by_status"].get(B15E.STATUS_UNAVAILABLE))
        self.assertEqual(12, counts["by_reason"].get(B15E.E06_ENTRY_NOT_PRICED))

    def test_a_censored_cell_is_never_scored_as_a_loss(self):
        counts = self._run([frame("S1", 1100)])
        self.assertGreater(counts["by_status"].get(B15E.STATUS_CENSORED, 0), 0)
        connection = sqlite3.connect(self.work / "shadow_paths.sqlite")
        rows = connection.execute(
            "SELECT net_return_lamports FROM position WHERE status=?",
            (B15E.STATUS_CENSORED,)).fetchall()
        connection.close()
        for (value,) in rows:
            self.assertIsNone(value, "a censored cell carries no return, not a negative one")

    def test_an_exited_cell_carries_exact_integer_figures(self):
        self._run([frame(f"S{slot}", slot) for slot in (1100, 2100, 3000)])
        connection = sqlite3.connect(self.work / "shadow_paths.sqlite")
        row = connection.execute(
            "SELECT exit_proceeds_lamports, exit_execution_cost_lamports, net_return_lamports "
            "FROM position WHERE status=? LIMIT 1", (B15E.STATUS_EXITED,)).fetchone()
        connection.close()
        self.assertIsNotNone(row)
        for value in row:
            self.assertIsInstance(value, int)

    def test_the_three_scenarios_produce_different_exit_costs(self):
        self._run([frame(f"S{slot}", slot) for slot in (1100, 2100, 3000)])
        connection = sqlite3.connect(self.work / "shadow_paths.sqlite")
        costs = {row[0] for row in connection.execute(
            "SELECT DISTINCT exit_execution_cost_lamports FROM position WHERE status=?",
            (B15E.STATUS_EXITED,))}
        connection.close()
        self.assertGreaterEqual(len(costs), 2, f"scenarios must differ on exit too: {costs}")

    def test_the_run_publishes_no_aggregate_across_scenarios(self):
        counts = self._run([frame(f"S{slot}", slot) for slot in (1100, 2100, 3000)])
        self.assertTrue(counts["no_aggregation_across_scenarios"])
        self.assertEqual("unmeasured", counts["market_impact"])
        self.assertEqual("unmeasured", counts["landing_probability"])

    def test_the_run_is_idempotent(self):
        frames = [frame(f"S{slot}", slot) for slot in (1100, 2100, 3000)]
        first = self._run(frames)
        second = self._run(frames)
        self.assertEqual(first["by_status"], second["by_status"])
        connection = sqlite3.connect(self.work / "shadow_paths.sqlite")
        self.assertEqual(12, connection.execute("SELECT COUNT(*) FROM position").fetchone()[0])
        connection.close()

    def test_upstream_evidence_is_never_written(self):
        raw = self.raw([frame("S1", 2100)])
        b15d = self.b15d(self._cells())
        before = (raw.read_bytes(), b15d.read_bytes())
        B15E.run(raw_path=raw, b15d_path=b15d, work_dir=self.work)
        self.assertEqual(before, (raw.read_bytes(), b15d.read_bytes()))

    def test_figures_are_withheld_until_the_cohort_is_complete(self):
        self._run([frame("S1", 1100)])
        report = B15E.status(db_path=self.work / "shadow_paths.sqlite")
        self.assertFalse(report["cohort_complete"])
        self.assertTrue(report["figures_withheld_until_cohort_complete"])
        self.assertIsNone(report["figures"])

    def test_the_status_line_is_redacted_and_labelled(self):
        self._run([frame(f"S{slot}", slot) for slot in (1100, 2100, 3000)])
        report = B15E.status(db_path=self.work / "shadow_paths.sqlite")
        PILOT.assert_redacted(report)
        self.assertEqual(B15E.LABEL, report["label"])
        self.assertFalse(report["executable"])
        self.assertTrue(report["not_b10c_state_in_force"])
        self.assertTrue(report["censored_never_scored_as_loss"])

    def test_a_missing_exit_cost_structure_stops_the_run(self):
        original = B10A.price_exit
        self.addCleanup(lambda: setattr(B10A, "price_exit", original))
        B10A.price_exit = lambda *a, **k: {"quote_lamports": 1}
        with self.assertRaisesRegex(Refused, "not a cost of zero"):
            self._run([frame(f"S{slot}", slot) for slot in (1100, 2100, 3000)])


class TestGates(Temp):
    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a different protocol"):
            B15E.verify_preregistration(expected_sha256="0" * 64)

    def test_no_execution_surface(self):
        self.assertTrue(B15E.assert_no_execution_surface())

    def test_a_planted_execution_surface_is_caught(self):
        for token in ("sendTransaction", "simulateTransaction", "Keypair"):
            with self.subTest(token=token):
                planted = self.directory / f"p_{token}.py"
                planted.write_text(f"x = {token}\n")
                with self.assertRaises(Refused):
                    B15E.assert_no_execution_surface(planted)

    def test_writing_into_upstream_evidence_is_refused(self):
        for marker in ("b15a", "b15b", "b15c", "b15d", "b11a"):
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    B15E.assert_isolated(ROOT / "research" / marker / "b15e")

    def test_a_directory_that_is_not_b15e_is_refused(self):
        with self.assertRaisesRegex(Refused, "must be .../b15e"):
            B15E.assert_isolated(self.directory / "elsewhere")

    def test_the_real_work_dir_passes(self):
        self.assertTrue(B15E.assert_isolated(B15E.WORK_DIR))

    def test_a_float_is_refused_as_this_modules_own_refusal(self):
        """Delegating bare would raise the PARENT class and slip past `except ShadowPathRefused`."""
        with self.assertRaises(Refused):
            B15E.assert_no_float({"net_return_lamports": 1.5})

    def test_the_freeze_forbids_the_claims_that_matter(self):
        forbidden = " ".join(self.document["strictly_forbidden"]).lower()
        for phrase in ("landing probability", "market impact", "censored", "denominator",
                       "aggregating across scenarios"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, forbidden)


if __name__ == "__main__":
    unittest.main()
