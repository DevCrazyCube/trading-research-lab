"""B16a guards. Synthetic fixtures throughout: no burned artifact is read and no network is used.

The guards that matter are the ones that would silently produce a wrong archetype rather than an
error: the account position the wallet is read from, the sign convention that decides whether a
position is still holding, the refusal to pair a wallet to a reserve delta when the transaction
carries more than one trade, and the ordering of the classification rules.
"""
import importlib.util
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B16A = load("b16a_operator_archetypes", "b16a_operator_archetypes.py")

CURVE = "Curve1111111111111111111111111111111111111"
WALLET = "Wallet111111111111111111111111111111111111"
OTHER = "Wallet222222222222222222222222222222222222"
CREATOR = "Creator11111111111111111111111111111111111"


class Fixture:
    """A throwaway pair of databases shaped like the burned artifacts."""

    def __init__(self, directory):
        self.directory = pathlib.Path(directory)
        self.b9d = self.directory / "b9d.sqlite"
        self.b10b = self.directory / "b10b.sqlite"
        self.identity = self.directory / "identity.sqlite"
        self._build()

    def _build(self):
        con = sqlite3.connect(self.b9d)
        con.executescript("""
            CREATE TABLE instruction (slot INTEGER, transaction_index INTEGER, outer_index INTEGER,
                inner_index INTEGER, signature TEXT, program_id TEXT, discriminator TEXT,
                idl_name TEXT, target INTEGER, accounts_json TEXT, data_len INTEGER);
            CREATE TABLE reserve_observation (slot INTEGER, transaction_index INTEGER,
                outer_index INTEGER, inner_index INTEGER, bonding_curve TEXT,
                virtual_quote_before INTEGER, virtual_token_before INTEGER,
                real_quote_before INTEGER, real_token_before INTEGER,
                virtual_quote_after INTEGER, virtual_token_after INTEGER,
                real_quote_after INTEGER, real_token_after INTEGER, evidence TEXT);
        """)
        con.commit()
        con.close()
        con = sqlite3.connect(self.b10b)
        con.executescript("""
            CREATE TABLE curve (bonding_curve TEXT, mint TEXT, create_slot INTEGER,
                create_transaction_index INTEGER, create_outer_index INTEGER,
                create_inner_index INTEGER, complete_slot INTEGER,
                complete_transaction_index INTEGER, trade_observations INTEGER, regime TEXT);
        """)
        con.commit()
        con.close()
        con = sqlite3.connect(self.identity)
        con.executescript("""
            CREATE TABLE identity (bonding_curve TEXT, mint TEXT, creator TEXT, create_user TEXT,
                t0_slot INTEGER, t0_transaction_index INTEGER, t0_outer_index INTEGER,
                t0_inner_index INTEGER, t0_kind TEXT, t0_user TEXT);
        """)
        con.commit()
        con.close()

    def curve(self, bonding_curve=CURVE, create_slot=1000, complete_slot=None, creator=CREATOR,
              create_user=CREATOR):
        con = sqlite3.connect(self.b10b)
        con.execute("INSERT INTO curve VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bonding_curve, "mint", create_slot, 0, 0, 0, complete_slot, None, 0, "r"))
        con.commit()
        con.close()
        con = sqlite3.connect(self.identity)
        con.execute("INSERT INTO identity VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bonding_curve, "mint", creator, create_user, create_slot, 0, 0, 0,
                     "TradeEvent", None))
        con.commit()
        con.close()

    def trade(self, slot, wallet, direction, quote, tokens, bonding_curve=CURVE,
              transaction_index=0, name=None, extra_instruction=False, reserves=True,
              accounts=None):
        """One trade: an instruction naming the wallet plus the reserve delta it caused."""
        name = name or ("buy" if direction == "buy" else "sell")
        index = B16A.USER_INDEX[name]
        account_list = accounts if accounts is not None else (
            ["x"] * index + [wallet] + ["y"] * 4)
        con = sqlite3.connect(self.b9d)
        con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (slot, transaction_index, 0, 0, f"sig{slot}-{transaction_index}", "pump", "d",
                     name, 1, json.dumps(account_list), 100))
        if extra_instruction:
            con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (slot, transaction_index, 1, 0, f"sig{slot}-{transaction_index}", "pump",
                         "d", name, 1, json.dumps(account_list), 100))
        if reserves:
            # Curve's point of view: a buy takes quote IN and sends tokens OUT.
            quote_delta = quote if direction == "buy" else -quote
            token_delta = -tokens if direction == "buy" else tokens
            con.execute("INSERT INTO reserve_observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (slot, transaction_index, 0, 0, bonding_curve, 0, 0, 1_000_000_000,
                         1_000_000_000_000, 0, 0, 1_000_000_000 + quote_delta,
                         1_000_000_000_000 + token_delta, "e"))
        con.commit()
        con.close()

    def run(self):
        return B16A.run(self.b9d, self.b10b, self.identity)

    def positions(self):
        trades, _excluded = B16A.load_trades(self.b9d)
        curves = B16A.load_curves(self.b10b, self.identity)
        positions = B16A.wallet_curve_positions(trades, curves)
        B16A.classify(positions)
        return positions


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b16a-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.fixture = Fixture(self.directory)


class TestWalletRecovery(Base):
    def test_the_wallet_is_read_from_the_idl_account_position(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        trades, _ = B16A.load_trades(self.fixture.b9d)
        self.assertEqual([t["wallet"] for t in trades], [WALLET])

    def test_a_short_account_list_is_excluded_not_guessed(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000, accounts=["a", "b"])
        trades, excluded = B16A.load_trades(self.fixture.b9d)
        self.assertEqual(trades, [])
        self.assertEqual(excluded["account_list_too_short"], 1)

    def test_the_validation_refuses_when_the_position_disagrees(self):
        """The guard that stops every archetype resting on an unchecked positional read."""
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        con = sqlite3.connect(self.fixture.identity)
        con.execute("UPDATE identity SET t0_slot=1001, t0_transaction_index=0, t0_user=?",
                    (OTHER,))
        con.commit()
        con.close()
        with self.assertRaisesRegex(B16A.AuditRefused, "not sound"):
            B16A.assert_user_index_is_sound(self.fixture.b9d, self.fixture.identity)

    def test_the_validation_passes_when_the_position_agrees(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        con = sqlite3.connect(self.fixture.identity)
        con.execute("UPDATE identity SET t0_slot=1001, t0_transaction_index=0, t0_user=?",
                    (WALLET,))
        con.commit()
        con.close()
        result = B16A.assert_user_index_is_sound(self.fixture.b9d, self.fixture.identity)
        self.assertEqual(result["validated_against_t0_user"], 1)
        self.assertEqual(result["disagreed"], 0)

    def test_the_validation_refuses_when_there_is_nothing_to_validate_against(self):
        with self.assertRaisesRegex(B16A.AuditRefused, "no t0_user"):
            B16A.assert_user_index_is_sound(self.fixture.b9d, self.fixture.identity)


class TestAmbiguityIsRefused(Base):
    def test_two_trade_instructions_in_one_transaction_are_excluded(self):
        """No evidence pairs wallet to reserve delta, so the pair is dropped and counted."""
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000, extra_instruction=True)
        trades, excluded = B16A.load_trades(self.fixture.b9d)
        self.assertEqual(trades, [])
        self.assertEqual(excluded["multiple_trade_instructions"], 2)

    def test_a_trade_with_no_reserve_observation_is_excluded(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000, reserves=False)
        trades, excluded = B16A.load_trades(self.fixture.b9d)
        self.assertEqual(trades, [])
        self.assertEqual(excluded["no_reserve_observation"], 1)

    def test_a_direction_contradicting_its_reserve_delta_is_excluded(self):
        """A 'buy' that took quote OUT of the curve is not understood, so it is not interpreted."""
        self.fixture.curve()
        con = sqlite3.connect(self.fixture.b9d)
        con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (1001, 0, 0, 0, "sig", "pump", "d", "buy", 1,
                     json.dumps(["x"] * 6 + [WALLET, "y"]), 100))
        con.execute("INSERT INTO reserve_observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (1001, 0, 0, 0, CURVE, 0, 0, 1_000_000_000, 1_000_000_000_000, 0, 0,
                     999_000_000, 1_000_000_000_000, "e"))
        con.commit()
        con.close()
        trades, excluded = B16A.load_trades(self.fixture.b9d)
        self.assertEqual(trades, [])
        self.assertEqual(excluded["direction_contradicts_reserve_delta"], 1)


class TestInventorySignConvention(Base):
    """The bug this suite exists to prevent: a holder reported as fully exited."""

    def test_a_buy_with_no_sell_leaves_inventory_unresolved(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        position = self.fixture.positions()[0]
        self.assertTrue(position["inventory_unresolved"])
        self.assertEqual(position["tokens_acquired"], 5_000)
        self.assertEqual(position["tokens_disposed"], 0)
        self.assertIsNone(position["exit_delay_slots"])

    def test_a_full_round_trip_resolves_the_inventory(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        self.fixture.trade(1050, WALLET, "sell", 120_000_000, 5_000, transaction_index=1)
        position = self.fixture.positions()[0]
        self.assertFalse(position["inventory_unresolved"])
        self.assertEqual(position["tokens_acquired"], 5_000)
        self.assertEqual(position["tokens_disposed"], 5_000)
        self.assertEqual(position["exit_delay_slots"], 49)
        self.assertEqual(position["observed_quote_flow_lamports"], 20_000_000)

    def test_a_partial_sell_still_leaves_inventory_unresolved(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        self.fixture.trade(1050, WALLET, "sell", 60_000_000, 2_000, transaction_index=1)
        position = self.fixture.positions()[0]
        self.assertTrue(position["inventory_unresolved"],
                        "selling part of a holding is not exiting it")

    def test_the_flow_is_never_called_profit_anywhere_in_the_module(self):
        source = (ROOT / "scripts" / "b16a_operator_archetypes.py").read_text()
        for banned in ("def profit", '"profit"', "'profit'", "pnl", "roi",
                       "expected_value", "return_on"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)


class TestClassification(Base):
    def test_a_creator_wallet_is_creator_like_even_when_it_snipes(self):
        """Ordered rules: the more specific observation wins."""
        self.fixture.curve(creator=WALLET, create_user=WALLET)
        self.fixture.trade(1000, WALLET, "buy", 100_000_000, 5_000)
        position = self.fixture.positions()[0]
        self.assertEqual(position["entry_delay_slots"], 0)
        self.assertEqual(position["archetype"], "creator_like_participant")

    def test_an_entry_at_or_after_completion_is_a_migration_trader(self):
        self.fixture.curve(complete_slot=1500)
        self.fixture.trade(1500, WALLET, "buy", 100_000_000, 5_000)
        self.assertEqual(self.fixture.positions()[0]["archetype"], "migration_trader")

    def test_an_immediate_entry_is_a_sniper(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        self.assertEqual(self.fixture.positions()[0]["archetype"], "immediate_launch_sniper")

    def test_a_far_later_entry_is_a_delayed_entrant(self):
        self.fixture.curve()
        self.fixture.trade(1000 + B16A.DELAYED_SLOTS, WALLET, "buy", 100_000_000, 5_000)
        self.assertEqual(self.fixture.positions()[0]["archetype"], "delayed_entrant")

    def test_a_wallet_entering_many_curves_early_is_a_repeat_entrant(self):
        for index in range(B16A.REPEAT_CURVES):
            curve = f"Curve{index}"
            self.fixture.curve(bonding_curve=curve, create_slot=1000 + index * 100)
            self.fixture.trade(1000 + index * 100, WALLET, "buy", 10_000_000, 500,
                               bonding_curve=curve, transaction_index=index)
        archetypes = {p["archetype"] for p in self.fixture.positions()}
        self.assertEqual(archetypes, {"repeat_early_entrant"})

    def test_one_fewer_curve_is_not_a_repeat_entrant(self):
        """The threshold does something; it is not decorative."""
        for index in range(B16A.REPEAT_CURVES - 1):
            curve = f"Curve{index}"
            self.fixture.curve(bonding_curve=curve, create_slot=1000 + index * 100)
            self.fixture.trade(1000 + index * 100, WALLET, "buy", 10_000_000, 500,
                               bonding_curve=curve, transaction_index=index)
        self.assertNotIn("repeat_early_entrant",
                         {p["archetype"] for p in self.fixture.positions()})

    def test_a_single_curve_mid_window_entry_is_incidental(self):
        self.fixture.curve()
        self.fixture.trade(1000 + B16A.IMMEDIATE_SLOTS + 1, WALLET, "buy", 100_000_000, 5_000)
        self.assertEqual(self.fixture.positions()[0]["archetype"], "incidental_trader")

    def test_a_position_on_a_curve_with_no_create_coordinate_is_dropped(self):
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        self.assertEqual(self.fixture.positions(), [])


class TestFeeSensitivity(Base):
    def test_the_documented_fee_is_charged_on_both_legs(self):
        position = {"quote_in_lamports": 1_000_000_000, "quote_out_lamports": 1_000_000_000}
        self.assertEqual(B16A._documented_curve_fee(position),
                         2_000_000_000 * B16A.DOCUMENTED_FEE_BPS // 10_000)

    def test_the_documented_rate_is_the_one_b15q_decoded(self):
        self.assertEqual(B16A.DOCUMENTED_FEE_BPS, 95)

    def test_the_fee_is_labelled_as_a_sensitivity_not_a_measurement(self):
        """The rate is documented in an ADJACENT population; saying otherwise would be a claim."""
        source = (ROOT / "scripts" / "b16a_operator_archetypes.py").read_text()
        self.assertIn("NOT a measured rate for these", source)
        self.assertIn("clearly-labelled sensitivity", source)

    def test_the_fee_adjusted_figure_is_reported_beside_the_raw_one(self):
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 1_000_000_000, 5_000)
        self.fixture.trade(1050, WALLET, "sell", 1_000_000_000, 5_000, transaction_index=1)
        con = sqlite3.connect(self.fixture.identity)
        con.execute("UPDATE identity SET t0_slot=1001, t0_transaction_index=0, t0_user=?",
                    (WALLET,))
        con.commit()
        con.close()
        block = self.fixture.run()["archetypes"]["immediate_launch_sniper"]
        raw = block["observed_quote_flow_lamports_where_fully_exited"]["median"]
        net = block["flow_less_documented_curve_fee_where_fully_exited"]["median"]
        self.assertEqual(raw, 0, "a flat round trip nets zero before fees")
        self.assertEqual(net, -19_000_000, "and 95 bps on each 1 SOL leg after them")


class TestReportHonesty(Base):
    def setUp(self):
        super().setUp()
        self.fixture.curve()
        self.fixture.trade(1001, WALLET, "buy", 100_000_000, 5_000)
        self.fixture.trade(1050, WALLET, "sell", 120_000_000, 5_000, transaction_index=1)
        con = sqlite3.connect(self.fixture.identity)
        con.execute("UPDATE identity SET t0_slot=1001, t0_transaction_index=0, t0_user=?",
                    (WALLET,))
        con.commit()
        con.close()
        self.report = self.fixture.run()

    def test_the_report_declares_itself_exploratory_and_not_executable(self):
        self.assertIn("EXPLORATORY", self.report["status"])
        self.assertFalse(self.report["executable"])
        self.assertEqual(self.report["performance_status"], "not_evaluated")
        self.assertEqual(self.report["execution_status"], "never_executed")

    def test_the_report_states_what_is_not_measurable(self):
        for key in ("profitability", "token_transfers", "identity_ownership",
                    "wallet_history_outside_the_window",
                    "executable_cost_and_capacity_per_wallet", "advertised_bot_features"):
            with self.subTest(key=key):
                self.assertIn(key, self.report["not_measurable_here"])

    def test_the_report_records_that_it_read_no_b11a_and_used_no_network(self):
        self.assertTrue(self.report["source"]["reads_no_b11a"])
        self.assertEqual(self.report["source"]["network"], "none")

    def test_the_report_carries_the_validation_result(self):
        self.assertEqual(self.report["wallet_recovery"]["validation"]["disagreed"], 0)

    def test_the_report_carries_the_exclusion_census(self):
        self.assertIn("excluded_from_trades", self.report["coverage"])
        self.assertIn("exclusions_are_refusals", self.report["coverage"])

    def test_the_module_reads_nothing_under_b11a(self):
        source = (ROOT / "scripts" / "b16a_operator_archetypes.py").read_text()
        self.assertNotIn("b11a", source.replace("reads_no_b11a", "").replace(
            "under `research/b11a`", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
