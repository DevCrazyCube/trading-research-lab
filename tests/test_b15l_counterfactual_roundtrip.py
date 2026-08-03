"""B15l tests. Every refusal is driven, and the arithmetic is checked against B10a rather than
against my own expectation of it.

The thing most worth breaking here is the transport: an additive carry that quietly admits a state
the chain could never have reached would produce a plausible number with nothing behind it. So each
condition that makes the carry indefensible is constructed, not argued about.
"""
import copy
import importlib.util
import json
import pathlib
import random
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


B15L = _load("b15l_counterfactual_roundtrip", "b15l_counterfactual_roundtrip.py")
B10A, B9I = B15L.B10A, B15L.B9I

NATIVE = B15L.NATIVE_QUOTE_MINT
CURVE = "Curve11111111111111111111111111111111111111"
MINT = "Mint111111111111111111111111111111111111111"
POSITION = 100_000_000

SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
POLICY = {"base_fee_lamports": 5000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
          "ata_rent_lamports": 2_039_280, "failed_attempts": 0}


def entry_checkpoint(**overrides):
    """A launch-shaped curve: the pinned Pump initial reserves."""
    record = {"signature": "Sig1", "delay_slots": 1, "bonding_curve": CURVE, "mint": MINT,
              "context_slot": 1000, "lateness_slots": 0,
              "virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
              "real_quote": 0, "real_token": 793_100_000_000_000,
              "quote_mint": NATIVE, "mayhem_mode": False, "complete": False}
    record.update(overrides)
    return record


def exit_checkpoint(**overrides):
    """The same curve later, with some external flow having gone through it."""
    record = {"signature": "Sig1", "delay_slots": 1, "horizon": "h_1000_slots",
              "bonding_curve": CURVE, "mint": MINT, "context_slot": 2000, "lateness_slots": 0,
              "virtual_quote": 31_000_000_000, "virtual_token": 1_038_580_645_161_290,
              "real_quote": 1_000_000_000, "real_token": 758_680_645_161_290,
              "quote_mint": NATIVE, "mayhem_mode": False, "complete": False}
    record.update(overrides)
    return record


class TestPreregistration(unittest.TestCase):
    def test_the_freeze_is_pinned(self):
        document = B15L.verify_preregistration()
        self.assertEqual(document["preregistration_id"], "B15L_COUNTERFACTUAL_ROUNDTRIP_V1")
        self.assertTrue(document["committed_before_any_result"])

    def test_a_tampered_freeze_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            altered = pathlib.Path(directory) / "altered.json"
            document = json.loads(B15L.PREREG_PATH.read_bytes())
            document["frozen_inputs_taken_from_earlier_freezes_unchanged"][
                "position_lamports"] = 999
            altered.write_text(json.dumps(document))
            with self.assertRaises(B15L.CounterfactualRefused) as caught:
                B15L.verify_preregistration(altered)
            self.assertIn("pinned", str(caught.exception))

    def test_an_unreadable_freeze_refuses(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.verify_preregistration(ROOT / "research" / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15L.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        with tempfile.TemporaryDirectory() as directory:
            poisoned = pathlib.Path(directory) / "poisoned.py"
            poisoned.write_text("FORBIDDEN_OUTPUT_WORDS = ()\nx = 'sendTransaction'\n")
            with self.assertRaises(B15L.CounterfactualRefused) as caught:
                B15L.assert_no_execution_surface(poisoned)
            self.assertIn("sendTransaction", str(caught.exception))

    def test_the_frozen_inputs_match_their_sources(self):
        document = B15L.verify_preregistration()
        frozen = document["frozen_inputs_taken_from_earlier_freezes_unchanged"]
        self.assertEqual(frozen["position_lamports"], 100_000_000)
        self.assertEqual(frozen["entry_delays_slots"], [1, 2, 4])
        b15d = json.loads(
            (ROOT / "research" / "B15D_SHADOW_ROUTE_PREREGISTRATION.json").read_bytes())
        self.assertEqual(frozen["entry_delays_slots"], b15d["delay_scenarios"]["values"])
        keys = ("scenario_id", "base_fee_lamports", "priority_fee_lamports", "tip_lamports",
                "ata_rent_lamports", "failed_attempts")
        for mine, theirs in zip(frozen["cost_scenarios"], b15d["cost_scenarios"]):
            self.assertEqual({k: mine[k] for k in keys}, {k: theirs[k] for k in keys})

    def test_the_native_mint_comes_from_the_pinned_module(self):
        """A hand-copied literal refused 22,620 native checkpoints and looked like a data problem."""
        self.assertEqual(B15L.NATIVE_QUOTE_MINT, B10A.B9D.NATIVE_QUOTE_MINT)
        self.assertEqual(B15L.NATIVE_QUOTE_MINT, "1" * 32)


class TestUpdateRule(unittest.TestCase):
    def test_the_rule_holds_over_the_frozen_corpus(self):
        outcome = B15L.validate_update_rule()
        self.assertEqual(outcome["mismatches"], 0)
        self.assertGreater(outcome["pairs_checked"], 90_000)

    def test_a_missing_corpus_refuses_rather_than_assuming_the_rule(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.validate_update_rule(ROOT / "research" / "absent.sqlite")
        self.assertIn(B15L.L_UPDATE_RULE_UNVALIDATED, str(caught.exception))

    def test_a_corpus_where_virtual_and_real_disagree_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "fake.sqlite"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE observation(bonding_curve TEXT, slot INTEGER, "
                "transaction_index INTEGER, outer_index INTEGER, inner_index INTEGER, "
                "virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER, "
                "real_token INTEGER)")
            connection.executemany(
                "INSERT INTO observation VALUES ('C',?,0,0,0,?,?,?,?)",
                [(1, 100, 200, 100, 200), (2, 150, 180, 999, 180)])   # virtual moved, real did not
            connection.commit()
            connection.close()
            with self.assertRaises(B15L.CounterfactualRefused) as caught:
                B15L.validate_update_rule(path)
            self.assertIn("disagree on 1 of 1 pairs", str(caught.exception))

    def test_a_corpus_with_no_pairs_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "empty.sqlite"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE observation(bonding_curve TEXT, slot INTEGER, "
                "transaction_index INTEGER, outer_index INTEGER, inner_index INTEGER, "
                "virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER, "
                "real_token INTEGER)")
            connection.commit()
            connection.close()
            with self.assertRaises(B15L.CounterfactualRefused) as caught:
                B15L.validate_update_rule(path)
            self.assertIn("no consecutive observation pairs", str(caught.exception))


class TestTransportGates(unittest.TestCase):
    def test_a_clean_pair_is_transportable(self):
        self.assertTrue(B15L.assert_transportable(entry_checkpoint(), exit_checkpoint()))

    def test_a_different_curve_is_an_identity_mismatch(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.assert_transportable(entry_checkpoint(),
                                      exit_checkpoint(bonding_curve="Other"))
        self.assertIn(B15L.L_IDENTITY_MISMATCH, str(caught.exception))

    def test_a_different_mint_is_an_identity_mismatch(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.assert_transportable(entry_checkpoint(), exit_checkpoint(mint="Other"))
        self.assertIn(B15L.L_IDENTITY_MISMATCH, str(caught.exception))

    def test_a_non_native_quote_refuses_on_either_side(self):
        for side, kwargs in (("entry", {"quote_mint": "USDC"}), ("exit", {"quote_mint": "USDC"})):
            with self.subTest(side=side):
                entry = entry_checkpoint(**(kwargs if side == "entry" else {}))
                exit_state = exit_checkpoint(**(kwargs if side == "exit" else {}))
                with self.assertRaises(B15L.CounterfactualRefused) as caught:
                    B15L.assert_transportable(entry, exit_state)
                self.assertIn(B15L.L_NON_NATIVE_QUOTE, str(caught.exception))

    def test_mayhem_refuses_on_either_side(self):
        for side in ("entry", "exit"):
            with self.subTest(side=side):
                entry = entry_checkpoint(mayhem_mode=(side == "entry"))
                exit_state = exit_checkpoint(mayhem_mode=(side == "exit"))
                with self.assertRaises(B15L.CounterfactualRefused) as caught:
                    B15L.assert_transportable(entry, exit_state)
                self.assertIn(B15L.L_MAYHEM, str(caught.exception))

    def test_a_curve_complete_at_entry_refuses(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.assert_transportable(entry_checkpoint(complete=True), exit_checkpoint())
        self.assertIn(B15L.L_COMPLETE_AT_ENTRY, str(caught.exception))

    def test_a_curve_complete_by_exit_refuses_because_our_order_moved_the_instant(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.assert_transportable(entry_checkpoint(), exit_checkpoint(complete=True))
        self.assertIn(B15L.L_COMPLETE_BY_EXIT, str(caught.exception))
        self.assertIn("would have moved the instant it completed", str(caught.exception))

    def test_an_exit_before_the_entry_refuses(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.assert_transportable(entry_checkpoint(context_slot=2000),
                                      exit_checkpoint(context_slot=1999))
        self.assertIn(B15L.L_TIME_ORDER, str(caught.exception))

    def test_the_same_slot_is_admissible(self):
        self.assertTrue(B15L.assert_transportable(entry_checkpoint(context_slot=1000),
                                                  exit_checkpoint(context_slot=1000)))

    def test_a_stale_checkpoint_refuses(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.assert_fresh(entry_checkpoint(lateness_slots=151), 150, "entry")
        self.assertIn(B15L.L_STALE_CHECKPOINT, str(caught.exception))
        self.assertTrue(B15L.assert_fresh(entry_checkpoint(lateness_slots=150), 150, "entry"))

    def test_an_unknown_lateness_refuses_rather_than_passing(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.assert_fresh(entry_checkpoint(lateness_slots=None), 150, "entry")
        self.assertIn(B15L.L_STALE_CHECKPOINT, str(caught.exception))


class TestCounterfactualState(unittest.TestCase):
    def test_our_delta_moves_virtual_and_real_by_the_same_amount(self):
        entry, exit_state = entry_checkpoint(), exit_checkpoint()
        state, external, ours = B15L.counterfactual_exit_state(
            entry, exit_state, tokens_out=1_000_000, quote_in=POSITION)
        self.assertEqual(ours["virtual_quote"], ours["real_quote"])
        self.assertEqual(ours["virtual_token"], ours["real_token"])
        self.assertEqual(ours["virtual_quote"], POSITION)
        self.assertEqual(ours["virtual_token"], -1_000_000)

    def test_the_external_delta_is_exit_minus_entry(self):
        entry, exit_state = entry_checkpoint(), exit_checkpoint()
        _state, external, _ours = B15L.counterfactual_exit_state(
            entry, exit_state, tokens_out=1_000_000, quote_in=POSITION)
        for field in ("virtual_quote", "virtual_token", "real_quote", "real_token"):
            self.assertEqual(external[field], exit_state[field] - entry[field])

    def test_the_transported_state_is_the_exact_sum(self):
        entry, exit_state = entry_checkpoint(), exit_checkpoint()
        state, external, ours = B15L.counterfactual_exit_state(
            entry, exit_state, tokens_out=1_000_000, quote_in=POSITION)
        for field in ("virtual_quote", "virtual_token", "real_quote", "real_token"):
            self.assertEqual(state[field], entry[field] + ours[field] + external[field])

    def test_an_external_flow_the_counterfactual_curve_cannot_supply_refuses(self):
        """Somebody else's trade could not have executed as observed, and we will not guess."""
        entry = entry_checkpoint()
        drained = exit_checkpoint(real_token=0, virtual_token=1_000)
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.counterfactual_exit_state(entry, drained, tokens_out=1_000_000,
                                           quote_in=POSITION)
        self.assertIn(B15L.L_TRANSPORT_INDEFENSIBLE, str(caught.exception))
        self.assertIn("will not guess what they did instead", str(caught.exception))

    def test_impossible_counterfactual_reserves_refuse(self):
        entry = entry_checkpoint()
        # An external flow that removes all of the virtual quote.
        broken = exit_checkpoint(virtual_quote=1, real_quote=0, real_token=793_100_000_000_000)
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.counterfactual_exit_state(entry, broken, tokens_out=0, quote_in=-30_000_000_001)
        self.assertIn(B15L.L_IMPOSSIBLE_RESERVES, str(caught.exception))

    def test_a_float_anywhere_refuses(self):
        entry = entry_checkpoint()
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.counterfactual_exit_state(entry, exit_checkpoint(), tokens_out=1.5,
                                           quote_in=POSITION)
        self.assertIn(B15L.L_FLOAT_PRESENT, str(caught.exception))

    def test_a_float_reserve_refuses(self):
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.counterfactual_exit_state(entry_checkpoint(virtual_quote=30_000_000_000.0),
                                           exit_checkpoint(), tokens_out=1, quote_in=POSITION)
        self.assertIn(B15L.L_FLOAT_PRESENT, str(caught.exception))

    def test_assert_integer_rejects_bool_as_well_as_float(self):
        for value in (True, 1.0, "1", None):
            with self.subTest(value=value):
                with self.assertRaises(B15L.CounterfactualRefused):
                    B15L.assert_integer("x", value)
        self.assertEqual(B15L.assert_integer("x", 7), 7)


class TestDifferentialAgainstB10a(unittest.TestCase):
    """The arithmetic is B10a's, so it is checked against B10a rather than against my expectation."""

    def test_the_entry_matches_b10a_price_entry_exactly(self):
        entry = entry_checkpoint()
        state = {k: entry[k] for k in ("virtual_quote", "virtual_token", "real_quote", "real_token",
                                      "quote_mint", "mayhem_mode", "complete")}
        state["slot"] = entry["context_slot"]
        expected = B10A.price_entry(state, {"side": B10A.BUY, "quote_lamports": POSITION},
                                    SCHEDULE, POLICY)
        row = B15L.price_cell(entry, exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        self.assertEqual(row["tokens_acquired"], expected["tokens_out"])
        self.assertEqual(row["lamports_out_of_wallet_at_entry"],
                         expected["lamports_out_of_wallet"])
        self.assertEqual(row["entry_curve_fees"], expected["curve_fees"]["charged_total"])

    def test_the_tokens_match_the_pinned_b9i_formula(self):
        entry = entry_checkpoint()
        expected = B9I.tokens_out_for_exact_quote_in(
            entry["virtual_quote"], entry["virtual_token"], POSITION)
        row = B15L.price_cell(entry, exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        self.assertEqual(row["tokens_acquired"], expected)

    def test_the_exit_matches_b10a_price_exit_on_the_transported_state(self):
        entry, exit_state = entry_checkpoint(), exit_checkpoint()
        row = B15L.price_cell(entry, exit_state, SCHEDULE, POLICY, POSITION)
        transported, _external, _ours = B15L.counterfactual_exit_state(
            entry, exit_state, row["tokens_acquired"], POSITION)
        expected = B10A.price_exit(transported, row["tokens_acquired"], SCHEDULE, POLICY)
        self.assertEqual(row["lamports_into_wallet_at_exit"], expected["lamports_into_wallet"])
        self.assertEqual(row["exit_curve_fees"], expected["curve_fees"]["charged_total"])

    def test_the_net_is_exactly_exit_minus_entry(self):
        row = B15L.price_cell(entry_checkpoint(), exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        self.assertEqual(row["counterfactual_net_lamports"],
                         row["lamports_into_wallet_at_exit"]
                         - row["lamports_out_of_wallet_at_entry"])

    def test_a_round_trip_with_no_external_flow_loses_exactly_the_costs(self):
        """The clearest check available: same state twice, so the only movement is our own order."""
        entry = entry_checkpoint()
        same = exit_checkpoint(virtual_quote=entry["virtual_quote"],
                              virtual_token=entry["virtual_token"],
                              real_quote=entry["real_quote"], real_token=entry["real_token"])
        row = B15L.price_cell(entry, same, SCHEDULE, POLICY, POSITION)
        self.assertLess(row["counterfactual_net_lamports"], 0)
        # And the loss is at least the unrefundable rent plus both executions plus both curve fees.
        floor = (POLICY["ata_rent_lamports"] + row["entry_execution_lamports"]
                 + row["exit_execution_lamports"] - POLICY["ata_rent_lamports"]
                 + row["entry_curve_fees"] + row["exit_curve_fees"])
        self.assertLessEqual(row["counterfactual_net_lamports"], -floor + POLICY["ata_rent_lamports"])

    def test_every_reported_quantity_is_an_exact_integer(self):
        row = B15L.price_cell(entry_checkpoint(), exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        for key, value in row.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.assertIsInstance(value, int, key)

    def test_an_order_exceeding_the_reserves_is_refused_not_priced(self):
        tiny = entry_checkpoint(real_token=1)
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.price_cell(tiny, exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        self.assertIn(B15L.L_ENTRY_UNPRICEABLE, str(caught.exception))

    def test_an_exit_the_curve_cannot_pay_is_refused_not_priced(self):
        entry = entry_checkpoint()
        # Our own buy adds the quote, so drain it back out via the external delta.
        poor = exit_checkpoint(real_quote=0, virtual_quote=30_000_000_000)
        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.price_cell(entry, poor, SCHEDULE, POLICY, POSITION)
        self.assertIn(B15L.L_EXIT_UNPRICEABLE, str(caught.exception))


class TestExitStatusGuard(unittest.TestCase):
    def test_an_exit_that_returns_an_unavailable_status_is_refused(self):
        """B10a returns a non-priced status only for a complete curve, which is already refused.

        The guard is kept because it asserts B10a's contract rather than assuming it, and the pricer
        is injectable so the branch can actually be provoked.
        """
        def unavailable(_state, tokens_in, _schedule, _policy):
            return {"side": "sell", "status": B10A.STATUS_EXIT_UNAVAILABLE,
                    "liquidity": B10A.L3_CURVE_COMPLETE, "tokens_in": tokens_in}

        with self.assertRaises(B15L.CounterfactualRefused) as caught:
            B15L.price_cell(entry_checkpoint(), exit_checkpoint(), SCHEDULE, POLICY, POSITION,
                            exit_pricer=unavailable)
        self.assertIn(B15L.L_EXIT_UNPRICEABLE, str(caught.exception))
        self.assertIn(B10A.L3_CURVE_COMPLETE, str(caught.exception))

    def test_the_real_pricer_still_prices(self):
        row = B15L.price_cell(entry_checkpoint(), exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        self.assertGreater(row["lamports_into_wallet_at_exit"], 0)


class TestArtifactLoading(unittest.TestCase):
    def test_a_missing_artifact_refuses_rather_than_reading_as_empty(self):
        for loader, label in ((B15L.load_entries, "B15i"), (B15L.load_exits, "B15f")):
            with self.subTest(label=label):
                with self.assertRaises(B15L.CounterfactualRefused) as caught:
                    loader(ROOT / "research" / "absent_artifact.sqlite")
                self.assertIn(f"no {label} artifact at", str(caught.exception))

    def test_the_real_artifacts_load(self):
        entries = B15L.load_entries()
        exits = B15L.load_exits()
        self.assertGreater(len(entries), 0)
        self.assertGreater(len(exits), 0)
        # Identity columns come from `schedule`, joined, not from `checkpoint` where they do not
        # exist. A missing join would have left every exit naming None and refused every cell.
        for record in list(exits.values())[:20]:
            self.assertIsNotNone(record["bonding_curve"])
            self.assertIsNotNone(record["mint"])


class TestSelfImpactDiagnostic(unittest.TestCase):
    def test_the_naive_figure_is_reported_beside_the_counterfactual(self):
        row = B15L.price_cell(entry_checkpoint(), exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        self.assertIsNotNone(row["naive_unreacting_exit_net_lamports"])
        self.assertEqual(row["self_impact_lamports"],
                         row["lamports_into_wallet_at_exit"]
                         - row["naive_unreacting_exit_net_lamports"])

    def test_a_naive_figure_that_cannot_be_priced_is_absent_never_zero(self):
        """On the live data this is the majority case: the observed curve holds ~1 lamport."""
        entry = entry_checkpoint()
        # No external quote flow, so our own buy is the ONLY quote the counterfactual curve holds:
        # the counterfactual sale is payable and the naive one is not.
        exit_state = exit_checkpoint(virtual_quote=entry["virtual_quote"],
                                     virtual_token=entry["virtual_token"], real_quote=1,
                                     real_token=entry["real_token"])
        row = B15L.price_cell(entry, exit_state, SCHEDULE, POLICY, POSITION)
        self.assertIsNone(row["naive_unreacting_exit_net_lamports"])
        self.assertIsNone(row["self_impact_lamports"])

    def test_the_self_impact_is_positive_when_our_own_buy_deepens_the_curve(self):
        row = B15L.price_cell(entry_checkpoint(), exit_checkpoint(), SCHEDULE, POLICY, POSITION)
        self.assertGreater(row["self_impact_lamports"], 0)


class TestSummaryAndLabels(unittest.TestCase):
    def test_an_empty_group_still_carries_its_labels(self):
        summary = B15L.summarise([])
        self.assertEqual(summary["priced_cells"], 0)
        self.assertEqual(summary["label"], B15L.LABEL)
        self.assertEqual(summary["assumption"], B15L.ASSUMPTION)

    def test_the_summary_publishes_no_mean(self):
        rows = [B15L.price_cell(entry_checkpoint(), exit_checkpoint(), SCHEDULE, POLICY, POSITION)]
        summary = B15L.summarise(rows)
        text = json.dumps(summary).lower()
        for banned in ("mean", "average", "expected"):
            self.assertNotIn(banned, text)

    def test_the_summary_counts_cells_at_or_below_zero(self):
        entry = entry_checkpoint()
        same = exit_checkpoint(virtual_quote=entry["virtual_quote"],
                              virtual_token=entry["virtual_token"],
                              real_quote=entry["real_quote"], real_token=entry["real_token"])
        rows = [B15L.price_cell(entry, same, SCHEDULE, POLICY, POSITION)]
        self.assertEqual(
            B15L.summarise(rows)["counterfactual_net_lamports"]["cells_at_or_below_zero"], 1)

    def test_a_field_named_after_a_return_is_refused(self):
        for word in ("return", "profit", "expected_value", "roi", "performance"):
            with self.subTest(word=word):
                with self.assertRaises(B15L.CounterfactualRefused) as caught:
                    B15L.assert_no_forbidden_words({f"net_{word}": 1})
                self.assertIn("no output of this study is a return", str(caught.exception))

    def test_the_status_locks_are_exempt_by_exact_name_only(self):
        """`performance_status` is a required disclaimer; `performance_summary` is the thing banned."""
        self.assertTrue(B15L.assert_no_forbidden_words(
            {"performance_status": "not_evaluated", "execution_status": "never_executed"}))
        for key in ("performance_summary", "performance", "status_performance"):
            with self.subTest(key=key):
                with self.assertRaises(B15L.CounterfactualRefused):
                    B15L.assert_no_forbidden_words({key: 1})

    def test_a_disclaimer_mentioning_the_word_is_not_a_violation(self):
        """The label says what this is not, so the scan must not fire on its own disclaimer."""
        self.assertTrue(B15L.assert_no_forbidden_words(
            {"note": "this is not a return and not a profit"}))


class TestStudyRun(unittest.TestCase):
    def _inputs(self):
        entries, exits, schedules = {}, {}, {}
        for index in range(4):
            signature = f"Sig{index}"
            schedules[signature] = SCHEDULE
            for delay in (1, 2, 4):
                entries[(signature, delay)] = entry_checkpoint(
                    signature=signature, delay_slots=delay,
                    bonding_curve=f"Curve{index}", mint=f"Mint{index}")
                for horizon in ("h_1000_slots", "h_10000_slots"):
                    exits[(signature, delay, horizon)] = exit_checkpoint(
                        signature=signature, delay_slots=delay, horizon=horizon,
                        bonding_curve=f"Curve{index}", mint=f"Mint{index}")
        return entries, exits, schedules

    def test_every_scenario_horizon_delay_group_is_reported_separately(self):
        entries, exits, schedules = self._inputs()
        report = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                          validate_rule=False)
        self.assertEqual(len(report["by_scenario_horizon_delay"]), 3 * 2 * 3)
        for key, group in report["by_scenario_horizon_delay"].items():
            self.assertEqual(group["priced_cells"], 4, key)

    def test_the_report_carries_every_required_label(self):
        entries, exits, schedules = self._inputs()
        report = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                          validate_rule=False)
        self.assertEqual(report["label"], "COUNTERFACTUAL_UNREACTING_BOOK")
        self.assertEqual(report["assumption"], "UNREACTING_ORDER_FLOW")
        self.assertFalse(report["executable"])
        self.assertEqual(report["landing_probability"], "unmeasured")
        self.assertEqual(report["competitor_response"], "unmeasured")
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertIn("censored by the recorders and not by the market",
                      report["censoring_statement"])

    def test_nothing_is_aggregated_across_horizons_or_scenarios(self):
        entries, exits, schedules = self._inputs()
        report = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                          validate_rule=False)
        for key in report["by_scenario_horizon_delay"]:
            scenario, horizon, delay = key.split("|")
            self.assertIn(scenario, ("optimistic", "base", "stressed"))
            self.assertIn(horizon, ("h_1000_slots", "h_10000_slots"))
            self.assertIn(delay, ("1", "2", "4"))
        # No key spans two horizons or two scenarios, and no total exists above them.
        self.assertNotIn("total", report)
        self.assertNotIn("all_horizons", report)

    def test_a_missing_entry_checkpoint_is_refused_and_counted(self):
        entries, exits, schedules = self._inputs()
        del entries[("Sig0", 1)]
        report = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                          validate_rule=False)
        self.assertEqual(report["refusals"][B15L.L_NO_ENTRY_CHECKPOINT], 3 * 2)

    def test_a_missing_fee_schedule_is_refused_and_never_assumed(self):
        entries, exits, schedules = self._inputs()
        del schedules["Sig0"]
        report = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                          validate_rule=False)
        self.assertEqual(report["refusals"][B15L.L_NO_FEE_SCHEDULE], 3 * 2 * 3)

    def test_the_result_is_identical_under_row_permutation(self):
        entries, exits, schedules = self._inputs()
        first = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                         validate_rule=False)
        shuffled_entries = dict(random.Random(11).sample(list(entries.items()), len(entries)))
        shuffled_exits = dict(random.Random(12).sample(list(exits.items()), len(exits)))
        second = B15L.run(b15i_path=shuffled_entries, b15f_path=shuffled_exits,
                          schedules=dict(random.Random(13).sample(list(schedules.items()),
                                                                  len(schedules))),
                          validate_rule=False)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_the_run_is_deterministic_when_repeated(self):
        entries, exits, schedules = self._inputs()
        one = B15L.run(b15i_path=copy.deepcopy(entries), b15f_path=copy.deepcopy(exits),
                       schedules=schedules, validate_rule=False)
        two = B15L.run(b15i_path=copy.deepcopy(entries), b15f_path=copy.deepcopy(exits),
                       schedules=schedules, validate_rule=False)
        self.assertEqual(json.dumps(one, sort_keys=True), json.dumps(two, sort_keys=True))

    def test_a_stale_checkpoint_is_refused_by_the_run(self):
        entries, exits, schedules = self._inputs()
        entries[("Sig0", 1)] = entry_checkpoint(signature="Sig0", delay_slots=1,
                                                bonding_curve="Curve0", mint="Mint0",
                                                lateness_slots=151)
        report = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                          validate_rule=False)
        self.assertEqual(report["refusals"][B15L.L_STALE_CHECKPOINT], 3 * 2)

    def test_the_run_validates_the_update_rule_by_default(self):
        entries, exits, schedules = self._inputs()
        report = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules)
        self.assertEqual(report["update_rule"]["mismatches"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
