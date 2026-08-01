import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9i_quote_reproduction", ROOT / "scripts" / "b9i_quote_reproduction.py")
B9I = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9I)


class QuoteReproductionTests(unittest.TestCase):
    def test_legacy_buy_adds_one_even_when_ratio_divides_exactly(self):
        fields = {"ix_name": "buy", "is_buy": True,
                  "token_amount": 203_000_000_000_000, "quote_amount": 7_000_000_001}
        quantity, predicted, observed = B9I.reproduce_trade(
            30_000_000_000, 1_073_000_000_000_000, fields)
        self.assertEqual((quantity, predicted, observed),
                         ("net_quote", 7_000_000_001, 7_000_000_001))

    def test_established_fees_are_scoped_to_legacy_buy_and_sell(self):
        common = {"quote_amount": 10_001, "fee": 101, "fee_basis_points": 100,
                  "creator_fee": 51, "creator_fee_basis_points": 50,
                  "cashback": 26, "cashback_fee_basis_points": 25}
        self.assertEqual(set(B9I.reproduce_fees(dict(common, ix_name="buy"))),
                         {"fee", "creator_fee", "cashback"})
        self.assertEqual(B9I.reproduce_fees(dict(common, ix_name="buy_exact_sol_in")), {})

    def test_bare_unestablished_fee_name_fails_closed(self):
        with self.assertRaisesRegex(B9I.FreezeViolation, "cannot be reproduced"):
            B9I.assert_unestablished_not_requested("buyback_fee")
        with self.assertRaisesRegex(B9I.FreezeViolation, "cannot be reproduced"):
            B9I.assert_unestablished_not_requested(["fee_exact_input"])
        self.assertTrue(B9I.assert_unestablished_not_requested(["fee", "creator_fee"]))

    def test_an_unrecognised_instruction_stops_the_run(self):
        """A path with no pinned arithmetic must never fall through to a default.

        Exact-input and exact-token buys use different formulas, so a new buy variant silently
        taking either one would produce a confident wrong number rather than a refusal.
        """
        for fields in ({"ix_name": "buy_something_new", "is_buy": True,
                        "token_amount": 10, "quote_amount": 100},
                       {"ix_name": "liquidate", "is_buy": False,
                        "token_amount": 10, "quote_amount": 100}):
            with self.subTest(ix_name=fields["ix_name"]):
                with self.assertRaisesRegex(B9I.FreezeViolation, "no pinned quote arithmetic"):
                    B9I.reproduce_trade(30_000_000_000, 1_073_000_000_000_000, fields)

    def test_nonpositive_legacy_denominator_fails_closed(self):
        fields = {"ix_name": "buy", "is_buy": True, "token_amount": 10, "quote_amount": 1}
        with self.assertRaisesRegex(B9I.FreezeViolation, "whole virtual token reserve"):
            B9I.reproduce_trade(20, 10, fields)


if __name__ == "__main__":
    unittest.main()
