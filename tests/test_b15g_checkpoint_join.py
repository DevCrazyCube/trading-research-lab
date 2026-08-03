"""B15g — the join guards, each shown to be able to refuse.

What can go wrong here is a join that succeeds when it should not: an exit priced at a target that
precedes its entry, a fee schedule assumed because the account carries none, a pending target
leaking into a published sum, a retrospective B15e cell smuggled into a prospective population, or
two rows matching one key and one of them silently winning.
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


B15G = _load("b15g_checkpoint_join", "b15g_checkpoint_join.py")
B15F, B15E, B15D, B15B, PILOT, B10A = (B15G.B15F, B15G.B15E, B15G.B15D, B15G.B15B, B15G.PILOT,
                                       B15G.B10A)
Refused = B15G.JoinRefused

MINT = "1thX6LZfHDZZbBQTG5s2XkvGXqivXhSpqSGuKAM1oV5"
CURVE = "So11111111111111111111111111111111111111112"
DECODER = B15B.build_decoder()


def trade_payload(fee_bps=95, creator_bps=5, cashback_bps=0, buyback_bps=0, mint=MINT):
    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
    types = DECODER["types"]
    discriminator = bytes(next(e["discriminator"] for e in json.loads(
        (ROOT / "research" / "pump_idl_9c82f61.json").read_text())["events"]
        if e["name"] == "TradeEvent"))
    overrides = {"mint": mint, "is_buy": True, "fee_basis_points": fee_bps,
                 "creator_fee_basis_points": creator_bps,
                 "cashback_fee_basis_points": cashback_bps,
                 "buyback_fee_basis_points": buyback_bps,
                 "quote_mint": b9d.NATIVE_QUOTE_MINT}
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


def frame(signature, slot, **kwargs):
    payload = trade_payload(**kwargs)
    return {"frame_seq": slot, "session_id": "s", "received_wall_unix": 0.0,
            "received_monotonic_ns": 0, "commitment": "confirmed",
            "raw_notification_json": {"params": {"result": {
                "context": {"slot": slot},
                "value": {"signature": signature, "err": None,
                          "logs": [f"{PILOT.PROGRAM_DATA_PREFIX}"
                                   f"{base64.b64encode(payload).decode()}"]}}}}}


def observation(slot, **kwargs):
    payload = trade_payload(**kwargs)
    body = payload
    fields = DECODER["b7d"].read_struct(
        DECODER["b7d"].Cursor(body[8:]), DECODER["types"]["TradeEvent"], DECODER["types"])
    return {"slot": slot, "signature": f"S{slot}", "log_index": 0, "fields": fields}


class Temp(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15g-test-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.work = self.directory / "b15g"
        self.work.mkdir()
        self.document = B15G.verify_preregistration()

    def raw(self, frames):
        path = self.directory / "raw.jsonl"
        with path.open("w") as handle:
            for item in frames:
                handle.write(json.dumps(item) + "\n")
        return path

    def b15f(self, rows, checkpoints=()):
        path = self.directory / "checkpoints.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(B15F.SCHEMA)
        for signature, delay, horizon, t0, target, state, reason in rows:
            connection.execute(
                "INSERT OR REPLACE INTO schedule(entry_signature,delay_slots,horizon,mint,"
                "bonding_curve,t0_slot,target_slot,state,reason,scheduled_at_wall_unix,"
                "scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,0.0,0)",
                (signature, delay, horizon, MINT, CURVE, t0, target, state, reason))
        for signature, delay, horizon, target, context, lateness, complete in checkpoints:
            connection.execute(
                "INSERT OR REPLACE INTO checkpoint(entry_signature,delay_slots,horizon,"
                "target_slot,context_slot,lateness_slots,virtual_quote,virtual_token,real_quote,"
                "real_token,quote_mint,mayhem_mode,complete,evidence_sha256,observed_at_wall_unix)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'e',0.0)",
                (signature, delay, horizon, target, context, lateness, 31_000_000_000,
                 1_000_000_000_000, 1_000_000_000, 700_000_000_000,
                 _load("b9d_transaction_bodies", "b9d_transaction_bodies.py").NATIVE_QUOTE_MINT,
                 0, int(complete)))
        connection.commit()
        connection.close()
        return path

    def b15d(self, cells):
        path = self.directory / "shadow_entries.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(B15D.SCHEMA)
        for signature, delay, scenario, obs_slot, status, tokens, outlay in cells:
            connection.execute(
                "INSERT OR REPLACE INTO candidate(signature,scenario_id,delay_slots,mint,t0_slot,"
                "observation_slot,status,tokens_out,total_outlay_lamports,evidence_sha256,"
                "priced_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,'e',0.0)",
                (signature, scenario, delay, MINT, 1000, obs_slot, status, tokens, outlay))
        connection.commit()
        connection.close()
        return path


class TestPopulation(Temp):
    def test_only_prospective_targets_enter(self):
        self.assertIn("ONLY targets scheduled prospectively",
                      self.document["population"]["rule"])
        self.assertIn("C_PRE_CHECKPOINT_PROTOCOL",
                      self.document["population"]["excluded_by_construction"])

    def test_not_scheduled_rows_are_excluded_by_the_query(self):
        b15f = self.b15f([
            ("Past", 1, "h_1000_slots", 100, 1101, B15F.STATE_NOT_SCHEDULED,
             B15F.C_PRE_CHECKPOINT_PROTOCOL),
            ("Future", 1, "h_1000_slots", 5000, 6001, B15F.STATE_SCHEDULED, None)])
        rows = B15G.prospective_targets(b15f)
        self.assertEqual(["Future"], [r[0] for r in rows])

    def test_no_b15e_identifier_appears_in_this_module(self):
        """Separate populations; a difference between them would measure the definitions."""
        source = (ROOT / "scripts" / "b15g_checkpoint_join.py").read_text()
        body = source.split("FORBIDDEN_TARGET_NAMES = (", 1)[-1].split(")", 1)[-1]
        for token in ("shadow_paths.sqlite", "b15e_shadow_path", "STATUS_CENSORED"):
            with self.subTest(token=token):
                self.assertNotIn(token, body)


class TestTargetSemantics(Temp):
    def test_the_right_label_passes(self):
        self.assertTrue(B15G.assert_target_semantics(B15G.TARGET_SEMANTICS))

    def test_every_other_target_rule_is_refused_by_name(self):
        for name in B15G.FORBIDDEN_TARGET_NAMES:
            with self.subTest(name=name):
                with self.assertRaisesRegex(Refused, "waiting to be misfiled"):
                    B15G.assert_target_semantics(name)

    def test_the_label_is_on_every_row(self):
        b15f = self.b15f([("S", 1, "h_1000_slots", 1000, 2001, B15F.STATE_SCHEDULED, None)])
        B15G.run(raw_path=self.raw([]), b15d_path=self.b15d([]), b15f_path=b15f,
                 work_dir=self.work)
        connection = sqlite3.connect(self.work / "checkpoint_join.sqlite")
        labels = {row[0] for row in connection.execute(
            "SELECT DISTINCT target_semantics FROM joined")}
        connection.close()
        self.assertEqual({B15G.TARGET_SEMANTICS}, labels)


class TestGeometry(Temp):
    def test_an_entry_strictly_before_the_target_gives_the_hold(self):
        self.assertEqual(1000, B15G.assert_entry_before_target(1001, 2001))

    def test_an_entry_at_the_target_is_refused(self):
        with self.assertRaisesRegex(Refused, B15G.J_ENTRY_NOT_BEFORE_TARGET):
            B15G.assert_entry_before_target(2001, 2001)

    def test_an_entry_after_the_target_is_refused(self):
        """B15d's actual entry can land after the nominal target; selling then sells nothing."""
        with self.assertRaisesRegex(Refused, "never opened"):
            B15G.assert_entry_before_target(3000, 2001)

    def test_a_missing_slot_is_refused(self):
        with self.assertRaises(Refused):
            B15G.assert_entry_before_target(None, 2001)

    def test_a_late_entry_is_refused_end_to_end(self):
        b15f = self.b15f(
            [("S", 1, "h_1000_slots", 1000, 2001, B15F.STATE_CHECKPOINTED, None)],
            checkpoints=[("S", 1, "h_1000_slots", 2001, 2010, 9, False)])
        # The entry observation lands AFTER the nominal target.
        b15d = self.b15d([("S", 1, scenario, 2500, B15D.STATUS_PRICED, 3_000_000_000,
                           103_394_280) for scenario in ("optimistic", "base", "stressed")])
        counts = B15G.run(raw_path=self.raw([frame("F", 1500)]), b15d_path=b15d,
                          b15f_path=b15f, work_dir=self.work)
        self.assertEqual(0, counts["by_state"].get(B15G.STATE_PRICED, 0))
        self.assertEqual(3, counts["by_reason"].get(B15G.J_ENTRY_NOT_BEFORE_TARGET))


class TestFeeSchedule(Temp):
    def test_the_schedule_comes_from_the_last_event_at_or_before_the_target(self):
        observations = [observation(1500, fee_bps=10), observation(1900, fee_bps=42),
                        observation(2500, fee_bps=99)]
        schedule, slot = B15G.fee_schedule_at_or_before(observations, 2001)
        self.assertEqual(42, schedule["fee_bps"], "the last one at or before, not the newest")
        self.assertEqual(1900, slot)

    def test_nothing_after_the_target_is_read(self):
        observations = [observation(2500, fee_bps=99)]
        with self.assertRaisesRegex(Refused, B15G.J_NO_FEE_EVIDENCE):
            B15G.fee_schedule_at_or_before(observations, 2001)

    def test_an_absent_schedule_is_refused_not_defaulted(self):
        """The account publishes no basis points at all, so there is nothing to fall back on."""
        with self.assertRaisesRegex(Refused, "not assumed"):
            B15G.fee_schedule_at_or_before([], 2001)

    def test_a_partial_schedule_is_refused(self):
        """fee_basis_points present but a sibling missing: still not a schedule."""
        partial = observation(1900)
        partial["fields"]["creator_fee_basis_points"] = None
        with self.assertRaisesRegex(Refused, "does not publish"):
            B15G.fee_schedule_at_or_before([partial], 2001)

    def test_the_account_layout_really_has_no_fee_fields(self):
        idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
        types = {t["name"]: t for t in idl["types"]}
        names = [f["name"] for f in types["BondingCurve"]["type"]["fields"]]
        self.assertEqual([], [n for n in names if "fee" in n or "basis" in n])

    def test_the_upstream_hardcoded_schedule_is_recorded_as_a_known_defect(self):
        defect = self.document["sell_fee_schedule"]["known_defect_upstream"]
        self.assertIn("b15f_checkpoint.py", defect["where"])
        self.assertIn("HARDCODED", defect["what"])
        self.assertIn("running worker", defect["why_b15f_is_not_edited"])


class TestCostPolicy(Temp):
    def _scenario(self):
        route = json.loads(
            (ROOT / "research" / "B15E_SHADOW_PATH_PREREGISTRATION.json").read_text())
        return next(s for s in route["exit_cost_scenarios"] if s["scenario_id"] == "base")

    def test_a_complete_policy_passes(self):
        policy = B15G.cost_policy(self._scenario())
        self.assertEqual(set(B10A.REQUIRED_POLICY_FIELDS), set(policy))

    def test_a_missing_component_is_refused_not_zeroed(self):
        for field in B10A.REQUIRED_POLICY_FIELDS:
            with self.subTest(field=field):
                scenario = dict(self._scenario())
                scenario.pop(field)
                with self.assertRaisesRegex(Refused, B15G.J_COST_ABSENT):
                    B15G.cost_policy(scenario)

    def test_a_float_component_is_refused(self):
        scenario = dict(self._scenario(), priority_fee_lamports=1.0)
        with self.assertRaisesRegex(Refused, B15G.J_COST_ABSENT):
            B15G.cost_policy(scenario)

    def test_the_exit_tip_and_ata_rent_are_zero_for_stated_reasons(self):
        self.assertEqual(0, self._scenario()["tip_lamports"])
        self.assertEqual(0, self._scenario()["ata_rent_lamports"])
        self.assertIn("already paid", self.document["exit_pricing"]["ata_rent_justification"])
        self.assertIn("operator route choice",
                      self.document["exit_pricing"]["tip_justification"])

    def test_scenarios_must_match(self):
        self.assertTrue(B15G.assert_scenarios_match("base", "base"))
        with self.assertRaisesRegex(Refused, B15G.J_SCENARIO_MISMATCH):
            B15G.assert_scenarios_match("base", "stressed")


class TestEndToEnd(Temp):
    def _setup(self, entry_slot=1500, complete=False, state=B15F.STATE_CHECKPOINTED):
        b15f = self.b15f(
            [("S", 1, "h_1000_slots", 1000, 2001, state, None)],
            checkpoints=[("S", 1, "h_1000_slots", 2001, 2010, 9, complete)]
            if state == B15F.STATE_CHECKPOINTED else [])
        b15d = self.b15d([("S", 1, scenario, entry_slot, B15D.STATUS_PRICED, 3_000_000_000,
                           103_394_280) for scenario in ("optimistic", "base", "stressed")])
        raw = self.raw([frame("F", 1400, fee_bps=95)])
        return raw, b15d, b15f

    def test_a_clean_join_prices_all_three_scenarios(self):
        raw, b15d, b15f = self._setup()
        counts = B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        self.assertEqual(3, counts["by_state"].get(B15G.STATE_PRICED))
        connection = sqlite3.connect(self.work / "checkpoint_join.sqlite")
        rows = connection.execute(
            "SELECT scenario_id, effective_hold_slots, fee_bps, fee_schedule_slot, "
            "net_return_lamports FROM joined WHERE state=?", (B15G.STATE_PRICED,)).fetchall()
        connection.close()
        for scenario, hold, fee_bps, fee_slot, net in rows:
            with self.subTest(scenario=scenario):
                self.assertEqual(501, hold, "2001 - 1500")
                self.assertEqual(95, fee_bps)
                self.assertEqual(1400, fee_slot)
                self.assertIsInstance(net, int)

    def test_the_three_scenarios_cost_differently(self):
        raw, b15d, b15f = self._setup()
        B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        connection = sqlite3.connect(self.work / "checkpoint_join.sqlite")
        costs = {row[0] for row in connection.execute(
            "SELECT DISTINCT exit_execution_cost_lamports FROM joined WHERE state=?",
            (B15G.STATE_PRICED,))}
        connection.close()
        self.assertEqual(3, len(costs))

    def test_a_complete_curve_is_refused(self):
        raw, b15d, b15f = self._setup(complete=True)
        counts = B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        self.assertEqual(3, counts["by_reason"].get(B15G.J_CURVE_COMPLETE))

    def test_a_checkpointed_row_with_no_checkpoint_state_is_refused(self):
        """The schedule says checkpointed but no checkpoint row exists: a conflict, not a zero."""
        b15f = self.b15f(
            [("S", 1, "h_1000_slots", 1000, 2001, B15F.STATE_CHECKPOINTED, None)],
            checkpoints=[])
        b15d = self.b15d([("S", 1, scenario, 1500, B15D.STATUS_PRICED, 3_000_000_000,
                           103_394_280) for scenario in ("optimistic", "base", "stressed")])
        counts = B15G.run(raw_path=self.raw([frame("F", 1400)]), b15d_path=b15d,
                          b15f_path=b15f, work_dir=self.work)
        self.assertEqual(3, counts["by_reason"].get(B15G.J_IDENTITY_CONFLICT))

    def test_a_pricing_result_with_no_cost_structure_is_refused(self):
        original = B10A.price_exit
        self.addCleanup(lambda: setattr(B10A, "price_exit", original))
        B10A.price_exit = lambda *a, **k: {"quote_lamports": 1}
        raw, b15d, b15f = self._setup()
        counts = B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        self.assertEqual(3, counts["by_reason"].get(B15G.J_COST_ABSENT))
        self.assertEqual(0, counts["by_state"].get(B15G.STATE_PRICED, 0))

    def test_a_pending_target_is_recorded_pending_and_never_priced(self):
        raw, b15d, b15f = self._setup(state=B15F.STATE_SCHEDULED)
        counts = B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        self.assertEqual(3, counts["by_state"].get(B15G.STATE_PENDING))
        self.assertEqual(0, counts["by_state"].get(B15G.STATE_PRICED, 0))

    def test_an_unpriced_entry_is_kept_in_the_denominator(self):
        b15f = self.b15f(
            [("S", 1, "h_1000_slots", 1000, 2001, B15F.STATE_CHECKPOINTED, None)],
            checkpoints=[("S", 1, "h_1000_slots", 2001, 2010, 9, False)])
        counts = B15G.run(raw_path=self.raw([frame("F", 1400)]), b15d_path=self.b15d([]),
                          b15f_path=b15f, work_dir=self.work)
        self.assertEqual(3, counts["by_state"].get(B15G.STATE_ENTRY_UNPRICED))
        self.assertEqual(3, sum(counts["by_state"].values()))

    def test_a_refused_checkpoint_carries_its_code_through(self):
        b15f = self.b15f([("S", 1, "h_1000_slots", 1000, 2001, B15F.STATE_REFUSED,
                           f"{B15F.C_LATE}:too late")])
        counts = B15G.run(raw_path=self.raw([]), b15d_path=self.b15d([]), b15f_path=b15f,
                          work_dir=self.work)
        self.assertEqual(3, counts["by_state"].get(B15G.STATE_CHECKPOINT_REFUSED))
        self.assertEqual(3, counts["by_reason"].get(B15G.J_CHECKPOINT_REFUSED))

    def test_the_run_is_idempotent(self):
        raw, b15d, b15f = self._setup()
        first = B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        second = B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        self.assertEqual(first["by_state"], second["by_state"])
        connection = sqlite3.connect(self.work / "checkpoint_join.sqlite")
        self.assertEqual(3, connection.execute("SELECT COUNT(*) FROM joined").fetchone()[0])
        connection.close()

    def test_upstream_evidence_is_never_written(self):
        raw, b15d, b15f = self._setup()
        before = (raw.read_bytes(), b15d.read_bytes(), b15f.read_bytes())
        B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        self.assertEqual(before, (raw.read_bytes(), b15d.read_bytes(), b15f.read_bytes()))


class TestSliceClosureGating(Temp):
    def test_an_open_slice_publishes_no_sum(self):
        """A sum over what has resolved so far is a sum over the fastest-resolving cells."""
        b15f = self.b15f([
            ("Done", 1, "h_1000_slots", 1000, 2001, B15F.STATE_CHECKPOINTED, None),
            ("Open", 1, "h_1000_slots", 5000, 6001, B15F.STATE_SCHEDULED, None)],
            checkpoints=[("Done", 1, "h_1000_slots", 2001, 2010, 9, False)])
        b15d = self.b15d([("Done", 1, scenario, 1500, B15D.STATUS_PRICED, 3_000_000_000,
                           103_394_280) for scenario in ("optimistic", "base", "stressed")])
        B15G.run(raw_path=self.raw([frame("F", 1400)]), b15d_path=b15d, b15f_path=b15f,
                 work_dir=self.work)
        report = B15G.status(db_path=self.work / "checkpoint_join.sqlite")
        self.assertEqual(0, report["closed_slices"])
        self.assertIsNone(report["figures_for_closed_slices_only"])
        self.assertTrue(report["interim_sums_never_published"])

    def test_a_closed_slice_may_publish(self):
        raw, b15d, b15f = self._all_terminal()
        B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        report = B15G.status(db_path=self.work / "checkpoint_join.sqlite")
        self.assertGreater(report["closed_slices"], 0)
        self.assertIsNotNone(report["figures_for_closed_slices_only"])
        for name, figures in report["figures_for_closed_slices_only"].items():
            with self.subTest(slice=name):
                self.assertIn("denominator", figures)
                self.assertGreaterEqual(figures["denominator"], figures["priced_cells"])

    def _all_terminal(self):
        b15f = self.b15f(
            [("S", 1, "h_1000_slots", 1000, 2001, B15F.STATE_CHECKPOINTED, None)],
            checkpoints=[("S", 1, "h_1000_slots", 2001, 2010, 9, False)])
        b15d = self.b15d([("S", 1, scenario, 1500, B15D.STATUS_PRICED, 3_000_000_000,
                           103_394_280) for scenario in ("optimistic", "base", "stressed")])
        return self.raw([frame("F", 1400)]), b15d, b15f

    def test_the_denominator_includes_every_scheduled_target(self):
        raw, b15d, b15f = self._all_terminal()
        counts = B15G.run(raw_path=raw, b15d_path=b15d, b15f_path=b15f, work_dir=self.work)
        self.assertEqual(3, sum(counts["by_state"].values()))


class TestGates(Temp):
    def test_a_drifted_freeze_is_refused(self):
        with self.assertRaisesRegex(Refused, "a different contract"):
            B15G.verify_preregistration(expected_sha256="0" * 64)

    def test_no_execution_surface(self):
        self.assertTrue(B15G.assert_no_execution_surface())

    def test_a_planted_execution_surface_is_caught(self):
        for token in ("sendTransaction", "simulateTransaction", "Keypair"):
            with self.subTest(token=token):
                planted = self.directory / f"p_{token}.py"
                planted.write_text(f"x = {token}\n")
                with self.assertRaises(Refused):
                    B15G.assert_no_execution_surface(planted)

    def test_writing_into_upstream_evidence_is_refused(self):
        for marker in ("b15a", "b15d", "b15e", "b15f", "b11a"):
            with self.subTest(marker=marker):
                with self.assertRaises(Refused):
                    B15G.assert_isolated(ROOT / "research" / marker / "b15g")

    def test_a_directory_that_is_not_b15g_is_refused(self):
        with self.assertRaisesRegex(Refused, "must be .../b15g"):
            B15G.assert_isolated(self.directory / "elsewhere")

    def test_the_real_work_dir_passes(self):
        self.assertTrue(B15G.assert_isolated(B15G.WORK_DIR))

    def test_a_float_is_refused_as_this_modules_own_refusal(self):
        with self.assertRaises(Refused):
            B15G.assert_no_float({"net_return_lamports": 1.5})

    def test_the_status_line_is_redacted_and_labelled(self):
        b15f = self.b15f([("S", 1, "h_1000_slots", 1000, 2001, B15F.STATE_SCHEDULED, None)])
        B15G.run(raw_path=self.raw([]), b15d_path=self.b15d([]), b15f_path=b15f,
                 work_dir=self.work)
        report = B15G.status(db_path=self.work / "checkpoint_join.sqlite")
        PILOT.assert_redacted(report)
        self.assertEqual(B15G.LABEL, report["label"])
        self.assertFalse(report["executable"])
        self.assertTrue(report["never_mixed_with_b15e"])
        self.assertEqual("unmeasured", report["market_impact"])
        self.assertEqual(B15G.TARGET_SEMANTICS, report["target_semantics"])


if __name__ == "__main__":
    unittest.main()
