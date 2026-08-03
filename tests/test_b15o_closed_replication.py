"""B15o tests. Every way the gate could open early is driven, on synthetic evidence, while locked.

The property that matters most is that nothing is materialized from an unfinished population, so each
of the three closure conditions is satisfied alone and the gate must still refuse. The population
itself is drawn twice from shuffled evidence and must come out identical, because a membership that
varied with row order would not be a drawn population at all.
"""
import base64
import importlib.util
import json
import pathlib
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


B15O = _load("b15o_closed_replication", "b15o_closed_replication.py")
B15L, B15M, B15N = B15O.B15L, B15O.B15M, B15O.B15N
B15F = B15O.B15F
PILOT = _load("b15a_shadow_pilot", "b15a_shadow_pilot.py")
FIXTURES = _load("b15a_shadow_fixtures", "b15a_shadow_fixtures.py")

ACTIVATION = 436_984_352
NATIVE = B15L.NATIVE_QUOTE_MINT
DELAYS = (1, 2, 4)
HORIZONS = (("h_1000_slots", 1000), ("h_10000_slots", 10_000))
TOLERANCE = 150
SMALL = 5          # a small population size, so closure can be reached in a fixture


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15o_"))
        self.b15i = self.directory / "processed_feed.sqlite"
        self.b15n = self.directory / "exit_checkpoints.sqlite"
        self.work = self.directory / "b15o"
        self.document = B15O.verify_preregistration()
        self.small = json.loads(json.dumps(self.document))
        self.small["the_closed_population"]["size"] = SMALL

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    # -- synthetic evidence ------------------------------------------------------------------

    def write_b15n(self, launches, terminal=True, checkpoints=True, complete=False,
                   virtual_quote=31_000_000_000, real_quote=1_000_000_000):
        """B15N's schedule and checkpoint tables for a set of launches."""
        connection = sqlite3.connect(self.b15n)
        connection.executescript(B15N.SCHEMA)
        connection.execute("DELETE FROM schedule")
        connection.execute("DELETE FROM checkpoint")
        for signature, t0, mint, curve in launches:
            for delay in DELAYS:
                for horizon, slots in HORIZONS:
                    target = t0 + delay + slots
                    connection.execute(
                        "INSERT INTO schedule(signature,delay_slots,horizon,mint,bonding_curve,"
                        "t0_slot,target_slot,state,reason,attempts,fork_state_at_schedule,"
                        "observed_after_gap,scheduled_at_wall_unix,scheduled_at_slot) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (signature, delay, horizon, mint, curve, t0, target,
                         "checkpointed" if terminal else "scheduled", None, 1, "confirmed", 0,
                         0.0, t0))
                    if not checkpoints:
                        continue
                    connection.execute(
                        "INSERT INTO checkpoint(signature,delay_slots,horizon,target_slot,"
                        "context_slot,lateness_slots,virtual_quote,virtual_token,real_quote,"
                        "real_token,quote_mint,mayhem_mode,complete,fork_state_at_read,"
                        "chain_verdict,observed_after_gap,raw_sha256,latency_ns,attempts,"
                        "read_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (signature, delay, horizon, target, target, 0, virtual_quote,
                         1_038_580_645_161_290, real_quote, 758_680_645_161_290, NATIVE, 0,
                         int(complete), "confirmed", None, 0, "a" * 64, 1000, 1, 0.0))
        connection.commit()
        connection.close()

    def write_b15i(self, launches):
        """B15i's observation and target tables: the entry side of each cell."""
        connection = sqlite3.connect(self.b15i)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS observation(signature TEXT PRIMARY KEY, t0_slot INTEGER, "
            "mint TEXT, bonding_curve TEXT, fork_state TEXT, observed_after_gap INTEGER, "
            "chain_verdict TEXT)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS target(signature TEXT, delay_slots INTEGER, "
            "bonding_curve TEXT, context_slot INTEGER, lateness_slots INTEGER, "
            "virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER, "
            "real_token INTEGER, quote_mint TEXT, mayhem_mode INTEGER, complete INTEGER, "
            "state TEXT)")
        connection.execute("DELETE FROM observation")
        connection.execute("DELETE FROM target")
        for signature, t0, mint, curve in launches:
            connection.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?)",
                               (signature, t0, mint, curve, "confirmed", 0, "confirmed"))
            for delay in DELAYS:
                connection.execute(
                    "INSERT INTO target VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (signature, delay, curve, t0 + delay, 0, 30_000_000_000,
                     1_073_000_000_000_000, 0, 793_100_000_000_000, NATIVE, 0, 0, "captured"))
        connection.commit()
        connection.close()

    def launches(self, count, start=None):
        start = (ACTIVATION + 100) if start is None else start
        return [(f"Sig{index:04d}", start + index * 10, f"Mint{index}", f"Curve{index}")
                for index in range(count)]

    def closure_slot(self, launches):
        last = max(l[1] for l in launches)
        return last + max(DELAYS) + max(s for _n, s in HORIZONS) + TOLERANCE

    def draw(self, **kwargs):
        return B15O.draw_members(self.b15n, document=self.small, **kwargs)

    def state(self, current_slot=None):
        return B15O.closure_state(self.b15n, self.small, current_slot)


class TestFreeze(Base):
    def test_the_freeze_is_pinned(self):
        self.assertEqual(self.document["preregistration_id"], "B15O_CLOSED_REPLICATION_V1")
        self.assertTrue(self.document["committed_before_reading_any_strategy_quantity"])
        self.assertEqual(self.document["the_closed_population"]["size"], 5000)

    def test_a_tampered_freeze_refuses(self):
        altered = self.directory / "altered.json"
        document = json.loads(B15O.PREREG_PATH.read_bytes())
        document["the_closed_population"]["size"] = 10
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.verify_preregistration(altered)
        self.assertIn("pinned", str(caught.exception))

    def test_an_unreadable_freeze_refuses(self):
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.verify_preregistration(self.directory / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_both_replicated_studies_are_bound_by_hash(self):
        import hashlib
        for key, module in (("b15l", B15L), ("b15m", B15M)):
            bound = self.document["replicated_verbatim"][key]
            theirs = module.verify_preregistration()
            actual = hashlib.sha256(
                json.dumps(theirs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(bound["canonical_sha256"], actual, key)
            self.assertEqual(bound["preregistration_id"], theirs["preregistration_id"])

    def test_a_document_binding_the_wrong_study_id_refuses(self):
        """The id is checked before the hash, so a correct hash under a wrong name still refuses."""
        import hashlib
        altered = self.directory / "wrongid.json"
        document = json.loads(B15O.PREREG_PATH.read_bytes())
        document["replicated_verbatim"]["b15l"]["preregistration_id"] = "SOMETHING_ELSE_V1"
        altered.write_text(json.dumps(document))
        expected = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.verify_preregistration(altered, expected)
        self.assertIn("but the module verifies", str(caught.exception))

    def test_a_changed_replicated_study_refuses(self):
        """If the published study changed, what would be replicated is not what was published."""
        import hashlib
        altered = self.directory / "b15o.json"
        document = json.loads(B15O.PREREG_PATH.read_bytes())
        document["replicated_verbatim"]["b15l"]["canonical_sha256"] = "0" * 64
        altered.write_text(json.dumps(document))
        expected = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.verify_preregistration(altered, expected)
        self.assertIn("the published study has changed", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15O.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        poisoned = self.directory / "poisoned.py"
        poisoned.write_text("FORBIDDEN_SOURCE_ARTIFACTS = ()\nx = 'sendTransaction'\n")
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.assert_no_execution_surface(poisoned)
        self.assertIn("sendTransaction", str(caught.exception))

    def test_the_module_does_not_read_b15a_or_b15f(self):
        """The entire premise of the population, so it is asserted mechanically."""
        self.assertTrue(B15O.assert_no_forbidden_source())

    def test_a_reinstated_b15a_or_b15f_dependency_is_caught(self):
        for artifact in ("b15a/shadow.sqlite", "b15f/checkpoints.sqlite"):
            with self.subTest(artifact=artifact):
                poisoned = self.directory / "reinstated.py"
                poisoned.write_text(
                    f"FORBIDDEN_SOURCE_ARTIFACTS = ()\nSOURCE = 'research/{artifact}'\n")
                with self.assertRaises(B15O.ReplicationRefused) as caught:
                    B15O.assert_no_forbidden_source(poisoned)
                self.assertIn(B15O.O_FORBIDDEN_SOURCE, str(caught.exception))

    def test_the_comparison_declares_no_threshold(self):
        comparison = self.document["predeclared_comparison"]
        self.assertTrue(comparison["nature"].startswith("DESCRIPTIVE ONLY"))
        self.assertIn("no_pass_threshold_exists", comparison)
        # KEYS, not the whole text: the freeze's own prose says "no threshold", and a substring scan
        # would fire on the disclaimer that promises the thing it is checking for.
        keys = {key.lower() for key in comparison}
        for banned in ("tolerance", "threshold", "p_value", "criterion"):
            self.assertNotIn(banned, keys)


class TestMembership(Base):
    def test_the_first_n_are_drawn_in_canonical_order(self):
        launches = self.launches(SMALL + 3)
        self.write_b15n(launches)
        members, total = self.draw()
        self.assertEqual(total, SMALL + 3)
        self.assertEqual(len(members), SMALL)
        self.assertEqual([m["signature"] for m in members],
                         [l[0] for l in launches[:SMALL]])
        self.assertEqual([m["t0_slot"] for m in members],
                         sorted(m["t0_slot"] for m in members))

    def test_ties_on_slot_break_by_signature_then_mint(self):
        launches = [("SigB", ACTIVATION + 100, "MintA", "CurveB"),
                    ("SigA", ACTIVATION + 100, "MintB", "CurveA"),
                    ("SigC", ACTIVATION + 200, "MintC", "CurveC")]
        self.write_b15n(launches)
        members, _total = self.draw(size=3)
        self.assertEqual([m["signature"] for m in members], ["SigA", "SigB", "SigC"])

    def test_membership_is_identical_under_row_permutation(self):
        launches = self.launches(SMALL + 5)
        shuffled = list(launches)
        random.Random(11).shuffle(shuffled)
        self.write_b15n(shuffled)
        first, _ = self.draw()
        self.write_b15n(list(reversed(shuffled)))
        second, _ = self.draw()
        self.assertEqual([m["signature"] for m in first], [m["signature"] for m in second])
        self.assertEqual([m["signature"] for m in first], [l[0] for l in launches[:SMALL]])

    def test_two_draws_over_the_same_evidence_agree(self):
        self.write_b15n(self.launches(SMALL + 1))
        self.assertTrue(B15O.assert_membership_stable(self.b15n, self.small))

    def test_an_unstable_membership_refuses(self):
        self.write_b15n(self.launches(SMALL + 1))
        original = B15O.draw_members
        calls = {"n": 0}

        def wobbly(*args, **kwargs):
            calls["n"] += 1
            members, total = original(*args, **kwargs)
            if calls["n"] == 2:
                members = list(reversed(members))
            return members, total
        try:
            B15O.draw_members = wobbly
            with self.assertRaises(B15O.ReplicationRefused) as caught:
                B15O.assert_membership_stable(self.b15n, self.small)
            self.assertIn(B15O.O_MEMBERSHIP_UNSTABLE, str(caught.exception))
        finally:
            B15O.draw_members = original

    def test_a_pre_activation_launch_is_not_a_member(self):
        launches = [("SigOld", ACTIVATION, "MintOld", "CurveOld")] + self.launches(SMALL)
        self.write_b15n(launches)
        members, total = self.draw()
        self.assertNotIn("SigOld", [m["signature"] for m in members])
        self.assertEqual(total, SMALL)

    def test_a_missing_b15n_artifact_refuses_rather_than_drawing_nothing(self):
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.draw_members(self.directory / "absent.sqlite", document=self.small)
        self.assertIn(B15O.O_EVIDENCE_INSUFFICIENT, str(caught.exception))


class TestClosureGate(Base):
    def test_a_short_population_is_locked(self):
        self.write_b15n(self.launches(SMALL - 1))
        state = self.state(current_slot=10 ** 9)
        self.assertTrue(state["locked"])
        self.assertIn(B15O.O_POPULATION_OPEN, state["reasons"])
        self.assertEqual(state["launches_remaining"], 1)

    def test_a_full_population_before_the_last_deadline_is_locked(self):
        """The count alone would materialize before the last horizons were read."""
        launches = self.launches(SMALL)
        self.write_b15n(launches)
        deadline = self.closure_slot(launches)
        state = self.state(current_slot=deadline - 1)
        self.assertTrue(state["locked"])
        self.assertIn(B15O.O_NOT_MATURE, state["reasons"])
        self.assertEqual(state["slots_remaining"], 1)

    def test_an_unknown_slot_is_locked_rather_than_assumed_mature(self):
        self.write_b15n(self.launches(SMALL))
        state = self.state(current_slot=None)
        self.assertTrue(state["locked"])
        self.assertIn(B15O.O_NOT_MATURE, state["reasons"])

    def test_attempts_still_in_flight_keep_it_locked(self):
        """The slot alone would materialize while attempts were still running."""
        launches = self.launches(SMALL)
        self.write_b15n(launches, terminal=False)
        state = self.state(current_slot=self.closure_slot(launches))
        self.assertTrue(state["locked"])
        self.assertIn(B15O.O_ATTEMPTS_IN_FLIGHT, state["reasons"])
        self.assertGreater(state["attempts_in_flight"], 0)

    def test_terminality_alone_on_a_short_population_is_locked(self):
        """And terminality alone would materialize on a population that is not yet full."""
        self.write_b15n(self.launches(SMALL - 2), terminal=True)
        state = self.state(current_slot=10 ** 9)
        self.assertTrue(state["locked"])
        self.assertIn(B15O.O_POPULATION_OPEN, state["reasons"])

    def test_all_three_conditions_open_the_gate(self):
        launches = self.launches(SMALL)
        self.write_b15n(launches, terminal=True)
        state = self.state(current_slot=self.closure_slot(launches))
        self.assertFalse(state["locked"])
        self.assertEqual(state["reasons"], [])

    def test_the_last_deadline_uses_the_largest_delay_and_horizon_plus_tolerance(self):
        launches = self.launches(SMALL)
        self.write_b15n(launches)
        state = self.state(current_slot=10 ** 9)
        last = max(l[1] for l in launches)
        self.assertEqual(state["last_member_t0_slot"], last)
        self.assertEqual(state["last_deadline_slot"], last + 4 + 10_000 + 150)

    def test_closure_is_decided_on_the_last_member_not_the_last_launch(self):
        """Launches beyond the boundary must not delay or advance closure."""
        launches = self.launches(SMALL + 4)
        self.write_b15n(launches)
        state = self.state(current_slot=10 ** 9)
        self.assertEqual(state["last_member_t0_slot"], launches[SMALL - 1][1])

    def test_assert_closed_refuses_while_locked(self):
        self.write_b15n(self.launches(SMALL - 1))
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.assert_closed(self.b15n, self.small, 10 ** 9)
        self.assertIn("locked", str(caught.exception))

    def test_the_locked_state_reports_no_estimand_quantity(self):
        """A watcher that had to price a cell to know whether it may price a cell would have."""
        self.write_b15n(self.launches(SMALL - 1))
        state = B15O.status(self.work, self.b15n, self.small, current_slot=10 ** 9)
        text = json.dumps(state).lower()
        for banned in ("capacity", "counterfactual", "net_lamports", "self_impact", "priced"):
            self.assertNotIn(banned, text)
        self.assertTrue(state["reports_no_estimand_while_locked"])


class TestMaterialization(Base):
    def _closed(self, count=SMALL, **kwargs):
        launches = self.launches(count)
        self.write_b15n(launches, **kwargs)
        self.write_b15i(launches)
        return launches, self.closure_slot(launches)

    def test_materializing_while_locked_refuses_and_writes_nothing(self):
        launches = self.launches(SMALL - 1)
        self.write_b15n(launches)
        self.write_b15i(launches)
        with self.assertRaises(B15O.ReplicationRefused):
            B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                             current_slot=10 ** 9)
        self.assertFalse(B15O.artifact_path(self.work).exists())

    def test_a_closed_population_materializes_both_studies(self):
        _launches, slot = self._closed()
        outcome = B15O.materialize(self.work, self.b15i, self.b15n, self.small, current_slot=slot)
        report = outcome["report"]
        self.assertFalse(outcome["already_materialized"])
        self.assertEqual(report["population"]["members"], SMALL)
        self.assertIn("b15l_counterfactual", report["replicated"])
        self.assertIn("b15m_capacity", report["replicated"])
        self.assertEqual(report["replicated"]["b15l_counterfactual"]["label"],
                         "COUNTERFACTUAL_UNREACTING_BOOK")
        self.assertEqual(report["replicated"]["b15m_capacity"]["label"],
                         "LIQUIDITY_CAPACITY_DIAGNOSTIC")
        self.assertTrue(B15O.artifact_path(self.work).exists())

    def test_materializing_twice_reports_rather_than_recomputes(self):
        _launches, slot = self._closed()
        first = B15O.materialize(self.work, self.b15i, self.b15n, self.small, current_slot=slot)
        second = B15O.materialize(self.work, self.b15i, self.b15n, self.small, current_slot=slot)
        self.assertFalse(first["already_materialized"])
        self.assertTrue(second["already_materialized"])
        self.assertIn(B15O.O_ALREADY_MATERIALIZED, second["note"])
        self.assertEqual(json.dumps(first["report"]["replicated"], sort_keys=True),
                         json.dumps(second["report"]["replicated"], sort_keys=True))

    def test_the_report_carries_the_published_operands_by_hash(self):
        _launches, slot = self._closed()
        report = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                  current_slot=slot)["report"]
        for key in ("b15l", "b15m"):
            operand = report["published_operands"][key]
            self.assertEqual(len(operand["sha256"]), 64)
            self.assertTrue(operand["document"].startswith("research/"))

    def test_the_comparison_is_descriptive_and_declares_no_verdict(self):
        _launches, slot = self._closed()
        report = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                  current_slot=slot)["report"]
        comparison = report["comparison"]
        self.assertEqual(comparison["nature"], "DESCRIPTIVE ONLY")
        # KEYS again: the disclaimer legitimately contains the words it forbids as field names.
        keys = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    keys.add(str(key).lower())
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(report)
        for banned in ("verdict", "passed", "agreement", "pooled", "success"):
            self.assertNotIn(banned, keys)

    def test_the_report_names_no_field_after_a_return(self):
        _launches, slot = self._closed()
        report = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                  current_slot=slot)["report"]
        self.assertTrue(B15L.assert_no_forbidden_words(report["replicated"]["b15l_counterfactual"]))
        self.assertTrue(B15M.assert_no_forbidden_words(report["replicated"]["b15m_capacity"]))

    def test_withheld_exit_checkpoints_are_counted_and_excluded(self):
        """B15N records an unconfirmed launch's checkpoint and withholds it; so does this."""
        launches, slot = self._closed()
        connection = sqlite3.connect(self.b15n)
        connection.execute(
            "UPDATE checkpoint SET fork_state_at_read='unresolved', chain_verdict=NULL "
            "WHERE signature=?", (launches[0][0],))
        connection.commit()
        connection.close()
        report = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                  current_slot=slot)["report"]
        self.assertEqual(
            report["population"]["exit_checkpoints_withheld_pending_confirmation"],
            len(DELAYS) * len(HORIZONS))

    def test_a_missing_entry_artifact_refuses(self):
        _launches, slot = self._closed()
        with self.assertRaises(B15O.ReplicationRefused) as caught:
            B15O.materialize(self.work, self.directory / "absent.sqlite", self.b15n, self.small,
                             current_slot=slot)
        self.assertIn(B15O.O_EVIDENCE_INSUFFICIENT, str(caught.exception))

    def test_a_missing_published_finding_refuses_rather_than_comparing_to_nothing(self):
        _launches, slot = self._closed()
        original = dict(B15O.PUBLISHED)
        try:
            B15O.PUBLISHED["b15l"] = self.directory / "absent.md"
            with self.assertRaises(B15O.ReplicationRefused) as caught:
                B15O.materialize(self.work, self.b15i, self.b15n, self.small, current_slot=slot)
            self.assertIn(B15O.O_PUBLISHED_FIGURE_MISSING, str(caught.exception))
        finally:
            B15O.PUBLISHED.clear()
            B15O.PUBLISHED.update(original)

    def test_the_result_is_identical_under_evidence_permutation(self):
        launches = self.launches(SMALL)
        shuffled = list(launches)
        random.Random(3).shuffle(shuffled)
        self.write_b15n(shuffled)
        self.write_b15i(shuffled)
        slot = self.closure_slot(launches)
        first = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                 current_slot=slot)["report"]
        second_work = self.directory / "b15o_two"
        self.write_b15n(list(reversed(shuffled)))
        self.write_b15i(list(reversed(shuffled)))
        second = B15O.materialize(second_work, self.b15i, self.b15n, self.small,
                                  current_slot=slot)["report"]
        self.assertEqual(json.dumps(first["replicated"], sort_keys=True),
                         json.dumps(second["replicated"], sort_keys=True))
        self.assertEqual(json.dumps(first["population"]["first_member"], sort_keys=True),
                         json.dumps(second["population"]["first_member"], sort_keys=True))

    def test_a_completed_curve_at_exit_is_refused_by_b15ls_own_gate(self):
        launches, slot = self._closed(complete=True)
        # Synthetic launches have no preserved launch transaction, so without injected schedules
        # every cell would stop at L_NO_FEE_SCHEDULE before reaching the completion gate.
        schedules = {signature: {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                                 "buyback_fee_bps": 5000}
                     for signature, *_rest in launches}
        report = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                  current_slot=slot, schedules=schedules)["report"]
        refusals = report["replicated"]["b15l_counterfactual"]["refusals"]
        self.assertIn(B15L.L_COMPLETE_BY_EXIT, refusals)

    def test_a_priced_population_reaches_both_estimands(self):
        launches, slot = self._closed()
        schedules = {signature: {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                                 "buyback_fee_bps": 5000}
                     for signature, *_rest in launches}
        report = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                  current_slot=slot, schedules=schedules)["report"]
        priced = sum(group["priced_cells"] for group in
                     report["replicated"]["b15l_counterfactual"][
                         "by_scenario_horizon_delay"].values())
        self.assertGreater(priced, 0)
        capacity = report["replicated"]["b15m_capacity"]["capacity_by_horizon_delay"]
        self.assertTrue(any(group["cells"] > 0 for group in capacity.values()))

    def test_a_population_with_no_exit_checkpoints_still_materializes_a_census(self):
        launches = self.launches(SMALL)
        self.write_b15n(launches, checkpoints=False)
        self.write_b15i(launches)
        report = B15O.materialize(self.work, self.b15i, self.b15n, self.small,
                                  current_slot=self.closure_slot(launches))["report"]
        self.assertEqual(report["population"]["exit_checkpoints"], 0)
        self.assertEqual(report["replicated"]["b15m_capacity"]["population"]["exit_checkpoints"], 0)


class TestWatcher(Base):
    def test_the_watcher_reports_locked_and_materializes_nothing(self):
        launches = self.launches(SMALL - 1)
        self.write_b15n(launches)
        self.write_b15i(launches)
        last = B15O.watch(self.work, self.b15i, self.b15n, ticks=2,
                          slot_source=lambda: 10 ** 9, sleeper=lambda _s: None,
                          document=self.small)
        self.assertTrue(last["locked"])
        self.assertIn("refusal", last)
        self.assertFalse(B15O.artifact_path(self.work).exists())

    def test_the_watcher_uses_the_real_freeze_by_default(self):
        """The document is injectable for fixtures; unspecified, it is the committed freeze."""
        import inspect
        signature = inspect.signature(B15O.watch)
        self.assertIsNone(signature.parameters["document"].default)
        launches = self.launches(2)
        self.write_b15n(launches)
        self.write_b15i(launches)
        last = B15O.watch(self.work, self.b15i, self.b15n, ticks=1,
                          slot_source=lambda: 10 ** 9, sleeper=lambda _s: None)
        self.assertEqual(last["size_required"], 5000)     # the committed boundary, not a fixture's

    def test_the_watcher_materializes_once_when_the_gate_opens(self):
        launches = self.launches(SMALL)
        self.write_b15n(launches)
        self.write_b15i(launches)
        slots = iter([10, self.closure_slot(launches), self.closure_slot(launches)])
        last = B15O.watch(self.work, self.b15i, self.b15n, ticks=3,
                          slot_source=lambda: next(slots), sleeper=lambda _s: None,
                          document=self.small)
        self.assertFalse(last["locked"])
        self.assertTrue(last["materialized"])
        self.assertTrue(last["already_materialized"])   # the third tick reported, not recomputed
        self.assertTrue(B15O.artifact_path(self.work).exists())

    def test_a_transient_slot_error_does_not_end_the_watcher(self):
        """Its whole job is to wait, so an endpoint fault must not be what stops it waiting."""
        launches = self.launches(SMALL - 1)
        self.write_b15n(launches)
        self.write_b15i(launches)
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("endpoint down")
            return 10 ** 9

        last = B15O.watch(self.work, self.b15i, self.b15n, ticks=2, slot_source=flaky,
                          sleeper=lambda _s: None, document=self.small)
        self.assertEqual(calls["n"], 2)
        self.assertTrue(last["locked"])


class TestVerbatimReplication(Base):
    """Nothing about either estimand may differ from what was published."""

    def test_the_replicated_inputs_are_the_published_ones(self):
        b15l = B15L.verify_preregistration()[
            "frozen_inputs_taken_from_earlier_freezes_unchanged"]
        self.assertEqual(b15l["position_lamports"], 100_000_000)
        self.assertEqual(b15l["entry_delays_slots"], [1, 2, 4])
        self.assertEqual(b15l["exit_horizons"], ["h_1000_slots", "h_10000_slots"])
        self.assertEqual([s["scenario_id"] for s in b15l["cost_scenarios"]],
                         ["optimistic", "base", "stressed"])
        b15m = B15M.verify_preregistration()
        self.assertEqual(b15m["secondary_estimand_separately_named"]["grid_lamports"],
                         [1_000_000, 2_500_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000,
                          100_000_000])
        self.assertEqual(b15m["frozen_inputs_unchanged"][
            "capacity_search_upper_bound_lamports"], 100_000_000)

    def test_the_replication_calls_the_published_modules_rather_than_reimplementing(self):
        import inspect
        source = inspect.getsource(B15O.materialize)
        self.assertIn("B15L.run(", source)
        self.assertIn("B15M.run(", source)
        for banned in ("tokens_out_for_exact_quote_in", "quote_out_for_tokens_in",
                       "def price_", "def external_capacity"):
            self.assertNotIn(banned, source)

    def test_the_declared_comparison_quantities_are_fixed_in_the_freeze(self):
        quantities = self.document["predeclared_comparison"][
            "quantities_compared_and_fixed_here"]
        self.assertIn("b15l", quantities)
        self.assertIn("b15m", quantities)
        self.assertGreaterEqual(len(quantities["b15l"]), 5)
        self.assertGreaterEqual(len(quantities["b15m"]), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
