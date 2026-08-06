"""B16b guards. Synthetic fixtures; no burned artifact and no network.

The guards worth testing are the ones that would let an overclaim through: calling a position closed
when its inventory is unresolved, counting a launch-transaction buy as a later one, collapsing the
creator and create_user roles without saying so, and describing token transfers as unavailable when
the corpus in fact records them undecoded.
"""
import importlib.util
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest

import tests.test_b16a_operator_archetypes as A

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B16B = load("b16b_creator_flow_decomposition", "b16b_creator_flow_decomposition.py")
B16A = B16B.B16A

WALLET = A.WALLET
OTHER = A.OTHER
CURVE = A.CURVE


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b16b-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.fixture = A.Fixture(self.directory)

    def pin_t0(self, wallet, slot=1001, transaction_index=0):
        con = sqlite3.connect(self.fixture.identity)
        con.execute("UPDATE identity SET t0_slot=?, t0_transaction_index=?, t0_user=?",
                    (slot, transaction_index, wallet))
        con.commit()
        con.close()

    def run_report(self):
        return B16B.run(self.fixture.b9d, self.fixture.b10b, self.fixture.identity)

    def creator_round_trip(self, buy_slot=1200, buy_tx=1, sell_slot=1300):
        """A creator-like wallet that buys later and fully exits."""
        self.fixture.curve(creator=WALLET, create_user=WALLET, create_slot=1000)
        self.fixture.trade(buy_slot, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=buy_tx)
        self.fixture.trade(sell_slot, WALLET, "sell", 1_500_000_000, 5_000, transaction_index=2)
        self.pin_t0(WALLET, buy_slot, buy_tx)


class TestLaunchTransactionSplit(Base):
    def test_a_buy_in_the_create_transaction_is_recognised_as_launch_activity(self):
        self.fixture.curve(creator=WALLET, create_user=WALLET, create_slot=1000)
        # Same slot AND same transaction index as the create.
        self.fixture.trade(1000, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=0)
        self.fixture.trade(1300, WALLET, "sell", 1_500_000_000, 5_000, transaction_index=2)
        self.pin_t0(WALLET, 1000, 0)
        report = self.run_report()
        split = report["does_it_survive_excluding_launch_transaction_activity"]
        self.assertEqual(split["bought_in_the_create_transaction"]["positions"], 1)
        self.assertEqual(split["did_not_buy_in_the_create_transaction"]["positions"], 0)

    def test_a_later_buy_is_not_counted_as_launch_activity(self):
        self.creator_round_trip()
        split = self.run_report()["does_it_survive_excluding_launch_transaction_activity"]
        self.assertEqual(split["bought_in_the_create_transaction"]["positions"], 0)
        self.assertEqual(split["did_not_buy_in_the_create_transaction"]["positions"], 1)

    def test_the_same_slot_but_a_different_transaction_is_not_launch_activity(self):
        """The distinction the split rests on: same block is not the same transaction."""
        self.fixture.curve(creator=WALLET, create_user=WALLET, create_slot=1000)
        self.fixture.trade(1000, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=7)
        self.fixture.trade(1300, WALLET, "sell", 1_500_000_000, 5_000, transaction_index=8)
        self.pin_t0(WALLET, 1000, 7)
        split = self.run_report()["does_it_survive_excluding_launch_transaction_activity"]
        self.assertEqual(split["bought_in_the_create_transaction"]["positions"], 0)

    def test_the_two_subsets_partition_the_fully_exited_positions(self):
        self.creator_round_trip()
        report = self.run_report()
        split = report["does_it_survive_excluding_launch_transaction_activity"]
        total = (split["bought_in_the_create_transaction"]["positions"]
                 + split["did_not_buy_in_the_create_transaction"]["positions"])
        self.assertEqual(total, report["denominators"]["fully_exited"])


class TestUnresolvedIsExcludedNotZeroed(Base):
    def test_a_creator_still_holding_is_excluded_from_every_flow(self):
        self.fixture.curve(creator=WALLET, create_user=WALLET, create_slot=1000)
        self.fixture.trade(1200, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=1)
        self.pin_t0(WALLET, 1200, 1)
        report = self.run_report()
        self.assertEqual(report["denominators"]["creator_like_positions"], 1)
        self.assertEqual(report["denominators"]["fully_exited"], 0)
        self.assertEqual(
            report["denominators"]["inventory_unresolved_and_therefore_excluded_from_every_flow"],
            1)
        self.assertIsNone(
            report["headline_being_decomposed"]["observed_quote_flow_lamports"])

    def test_a_partial_exit_still_counts_as_unresolved(self):
        self.fixture.curve(creator=WALLET, create_user=WALLET, create_slot=1000)
        self.fixture.trade(1200, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=1)
        self.fixture.trade(1300, WALLET, "sell", 400_000_000, 2_000, transaction_index=2)
        self.pin_t0(WALLET, 1200, 1)
        report = self.run_report()
        self.assertEqual(report["denominators"]["fully_exited"], 0)

    def test_denominators_add_up(self):
        self.creator_round_trip()
        report = self.run_report()
        d = report["denominators"]
        self.assertEqual(
            d["creator_like_positions"],
            d["fully_exited"]
            + d["inventory_unresolved_and_therefore_excluded_from_every_flow"])


class TestRoleSeparation(Base):
    def test_a_wallet_named_by_both_fields_is_labelled_as_such(self):
        self.creator_round_trip()
        report = self.run_report()
        self.assertEqual(report["by_role"]["role_tally_over_all_creator_like_positions"],
                         {"both_fields_name_this_wallet": 1})

    def test_a_create_user_that_is_not_the_creator_is_separated(self):
        self.fixture.curve(creator=OTHER, create_user=WALLET, create_slot=1000)
        self.fixture.trade(1200, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=1)
        self.fixture.trade(1300, WALLET, "sell", 1_500_000_000, 5_000, transaction_index=2)
        self.pin_t0(WALLET, 1200, 1)
        report = self.run_report()
        self.assertEqual(report["by_role"]["role_tally_over_all_creator_like_positions"],
                         {"create_user_only": 1})

    def test_a_creator_that_is_not_the_create_user_is_separated(self):
        self.fixture.curve(creator=WALLET, create_user=OTHER, create_slot=1000)
        self.fixture.trade(1200, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=1)
        self.fixture.trade(1300, WALLET, "sell", 1_500_000_000, 5_000, transaction_index=2)
        self.pin_t0(WALLET, 1200, 1)
        report = self.run_report()
        self.assertEqual(report["by_role"]["role_tally_over_all_creator_like_positions"],
                         {"creator_only": 1})

    def test_the_report_states_the_roles_cannot_be_separated_in_this_corpus(self):
        self.creator_round_trip()
        self.assertIn("SAME wallet", self.run_report()["by_role"]["limit"])


class TestChannelsOutsideTheFlow(Base):
    def test_a_fee_channel_touching_the_wallet_is_counted_as_presence(self):
        self.creator_round_trip()
        con = sqlite3.connect(self.fixture.b9d)
        con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (1400, 5, 0, 0, "sigfee", "pump", "d", "collect_creator_fee", 1,
                     json.dumps(["a", WALLET, "b"]), 40))
        con.commit()
        con.close()
        channels = self.run_report()["channels_outside_the_flow"]
        self.assertEqual(channels["instructions_in_corpus"]["collect_creator_fee"], 1)
        self.assertEqual(
            channels["instructions_touching_a_creator_like_wallet"]["collect_creator_fee"], 1)

    def test_a_fee_channel_not_touching_the_wallet_is_counted_only_in_the_corpus_total(self):
        self.creator_round_trip()
        con = sqlite3.connect(self.fixture.b9d)
        con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (1400, 5, 0, 0, "sigfee", "pump", "d", "claim_cashback", 1,
                     json.dumps(["a", OTHER, "b"]), 40))
        con.commit()
        con.close()
        channels = self.run_report()["channels_outside_the_flow"]
        self.assertEqual(channels["instructions_in_corpus"]["claim_cashback"], 1)
        self.assertNotIn("claim_cashback",
                         channels["instructions_touching_a_creator_like_wallet"])

    def test_no_amount_is_claimed_for_a_fee_channel(self):
        """Presence only: an address in an instruction is not proof it was paid."""
        self.creator_round_trip()
        channels = self.run_report()["channels_outside_the_flow"]
        self.assertIn("amounts are not", channels["why_separate"])
        for key in channels:
            self.assertNotIn("lamports", key)

    def test_fee_channels_are_absent_from_the_curve_flow_by_construction(self):
        """A fee instruction must not move the flow figure, because it moves no curve reserve."""
        self.creator_round_trip()
        before = self.run_report()["headline_being_decomposed"][
            "observed_quote_flow_lamports"]["median"]
        con = sqlite3.connect(self.fixture.b9d)
        con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (1400, 5, 0, 0, "sigfee", "pump", "d", "collect_creator_fee_v2", 1,
                     json.dumps(["a", WALLET, "b"]), 40))
        con.commit()
        con.close()
        after = self.run_report()["headline_being_decomposed"][
            "observed_quote_flow_lamports"]["median"]
        self.assertEqual(before, after)


class TestTokenTransferHonesty(Base):
    def test_transfers_are_reported_as_recorded_but_undecoded_not_as_absent(self):
        """The overclaim this catches: I first wrote that transfers were invisible. They are not."""
        self.creator_round_trip()
        con = sqlite3.connect(self.fixture.b9d)
        con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (1500, 9, 0, 0, "sigtok", B16B.SPL_TOKEN, "d", None, 0, json.dumps([]), 10))
        con.commit()
        con.close()
        transfers = self.run_report()["token_transfers"]
        self.assertTrue(transfers["transfers_are_recorded_but_not_decoded"])
        self.assertEqual(transfers["token_program_instructions_present"][B16B.SPL_TOKEN], 1)
        self.assertEqual(transfers["token_program_instructions_decoded"], 0)
        self.assertIn("not", transfers["why"])

    def test_a_decoded_token_instruction_would_be_counted_as_decoded(self):
        self.creator_round_trip()
        con = sqlite3.connect(self.fixture.b9d)
        con.execute("INSERT INTO instruction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (1500, 9, 0, 0, "sigtok", B16B.TOKEN_2022, "d", "transfer", 0,
                     json.dumps([]), 10))
        con.commit()
        con.close()
        self.assertEqual(self.run_report()["token_transfers"][
            "token_program_instructions_decoded"], 1)


class TestClaimsNotMade(Base):
    def test_no_reported_quantity_is_labelled_profit(self):
        """The word may appear in the disclaimer -- that is where it belongs. What must never
        happen is a NUMBER keyed by it."""
        self.creator_round_trip()
        report = self.run_report()
        self.assertIn("not claimed", report["not_claimed"]["profit"])
        offenders = []

        def walk(node, trail=""):
            if isinstance(node, dict):
                for key, value in node.items():
                    if trail.startswith(".not_claimed"):
                        continue
                    lowered = str(key).lower()
                    if any(word in lowered for word in ("profit", "pnl", "gain", "roi",
                                                        "return")) and not isinstance(value, str):
                        offenders.append(f"{trail}.{key}")
                    walk(value, f"{trail}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{trail}[{index}]")

        walk(report)
        self.assertEqual(offenders, [], "a numeric field is presented as a result")

    def test_the_report_refuses_to_recommend_issuance(self):
        self.creator_round_trip()
        note = self.run_report()["not_claimed"]["issuance_as_a_strategy"]
        self.assertIn("not recommended", note)
        self.assertIn("not evaluated", note)

    def test_the_report_keeps_wallet_equality_apart_from_ownership(self):
        self.creator_round_trip()
        note = self.run_report()["wallet_equality_is_not_ownership"]
        self.assertIn("EQUAL to a recorded", note)
        self.assertIn("No clustering", note)

    def test_the_report_declares_itself_exploratory_and_not_executable(self):
        self.creator_round_trip()
        report = self.run_report()
        self.assertIn("EXPLORATORY", report["status"])
        self.assertFalse(report["executable"])
        self.assertEqual(report["performance_status"], "not_evaluated")

    def test_it_refuses_when_there_is_nothing_to_decompose(self):
        self.fixture.curve(creator=OTHER, create_user=OTHER, create_slot=1000)
        self.fixture.trade(1200, WALLET, "buy", 1_000_000_000, 5_000, transaction_index=1)
        self.pin_t0(WALLET, 1200, 1)
        with self.assertRaises(B16B.DecompositionRefused):
            self.run_report()


if __name__ == "__main__":
    unittest.main(verbosity=2)
