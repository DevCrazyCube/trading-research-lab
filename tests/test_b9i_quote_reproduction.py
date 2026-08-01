"""B9i exact integer quote and fee reproduction.

The arithmetic is the whole product here, so these tests are mostly about the boundary cases that
distinguish one integer form from another -- and about what the gate refuses to certify.
"""
import importlib.util
import pathlib
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9i_quote_reproduction", ROOT / "scripts" / "b9i_quote_reproduction.py")
B9I = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9I)

# One b9d instance, so FreezeViolation is the same class the assertions match. See the same note in
# test_b9g_decode_readiness.
B9D = B9DT.B9D
B9I.B9D = B9D
B9I.FreezeViolation = B9D.FreezeViolation


def trade(**overrides):
    fields = {"ix_name": "buy", "is_buy": True, "quote_amount": 100, "token_amount": 10,
              "fee_basis_points": 95, "fee": 1,
              "creator_fee_basis_points": 30, "creator_fee": 1,
              "cashback_fee_basis_points": 0, "cashback": 0,
              "buyback_fee_basis_points": 5000, "buyback_fee": 0}
    fields.update(overrides)
    return fields


class LegacyBuyRoundingTests(unittest.TestCase):
    """The one boundary that distinguishes floor+1 from ceil."""

    # The real discriminating observation: slot 433,988,917, the only exactly-divisible legacy buy
    # in 31,397. `ceil` yields 7,000,000,000; the program moved 7,000,000,001.
    VQ, VT, TOKEN = 30_000_000_000, 1_073_000_000_000_000, 203_000_000_000_000

    def test_an_exactly_divisible_legacy_buy_takes_the_extra_lamport(self):
        """This case is why B2b's 9 samples could not settle the form.

        ceil and floor+1 agree on every trade whose division leaves a remainder, so a sample
        without an exact division cannot tell them apart. The program adds the lamport
        unconditionally.
        """
        numerator, denominator = self.TOKEN * self.VQ, self.VT - self.TOKEN
        self.assertEqual(numerator % denominator, 0, "fixture must be the exact-division case")
        name, predicted, observed = B9I.reproduce_trade(
            self.VQ, self.VT, trade(token_amount=self.TOKEN, quote_amount=7_000_000_001))
        self.assertEqual(name, "net_quote")
        self.assertEqual(predicted, 7_000_000_001)
        self.assertEqual(predicted, observed)
        self.assertEqual(B9I.ceil_div(numerator, denominator), 7_000_000_000,
                         "ceil would have been one lamport short")

    def test_the_two_forms_still_agree_when_the_division_has_a_remainder(self):
        """Which is why 31,396 of 31,397 observations cannot distinguish them."""
        vq, vt, token = 30_000_000_000, 1_073_000_000_000_000, 200_000_000_001
        numerator, denominator = token * vq, vt - token
        self.assertNotEqual(numerator % denominator, 0)
        self.assertEqual(numerator // denominator + 1, B9I.ceil_div(numerator, denominator))

    def test_a_legacy_buy_consuming_the_whole_reserve_is_refused(self):
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9I.reproduce_trade(self.VQ, self.TOKEN, trade(token_amount=self.TOKEN))
        self.assertIn("whole virtual token reserve", str(ctx.exception))


class QuoteFormTests(unittest.TestCase):

    def test_each_instruction_family_uses_its_own_pinned_form(self):
        """Exact-input and exact-token buys must never share one formula -- B2b's original error."""
        vq, vt = 30_000_000_000, 1_073_000_000_000_000
        name, predicted, _ = B9I.reproduce_trade(
            vq, vt, trade(ix_name="buy_exact_sol_in", quote_amount=1_000_000, token_amount=0))
        self.assertEqual(name, "tokens_out")
        self.assertEqual(predicted, (1_000_000 - 1) * vt // (vq + 1_000_000 - 1))

        name, predicted, _ = B9I.reproduce_trade(
            vq, vt, trade(ix_name="sell", is_buy=False, token_amount=5_000, quote_amount=0))
        self.assertEqual(name, "quote_out")
        self.assertEqual(predicted, 5_000 * vq // (vt + 5_000))

    def test_an_unrecognised_instruction_stops_the_run(self):
        """A path with no pinned arithmetic must never fall through to a default."""
        for fields in (trade(ix_name="buy_something_new"),
                       trade(ix_name="liquidate", is_buy=False)):
            with self.subTest(ix_name=fields["ix_name"]):
                with self.assertRaises(B9D.FreezeViolation) as ctx:
                    B9I.reproduce_trade(30_000_000_000, 1_073_000_000_000_000, fields)
                self.assertIn("no pinned quote arithmetic", str(ctx.exception))

    def test_non_integer_trade_quantities_are_refused(self):
        for bad in ({"quote_amount": "100"}, {"token_amount": -1}, {"quote_amount": True}):
            with self.subTest(bad=bad):
                with self.assertRaises(B9D.FreezeViolation):
                    B9I.reproduce_trade(30_000_000_000, 1_073_000_000_000_000, trade(**bad))


class FeeScopeTests(unittest.TestCase):

    def test_fees_reproduce_on_legacy_buy_and_sell(self):
        fees = B9I.reproduce_fees(trade(quote_amount=1_000_000, fee=9_500, creator_fee=3_000))
        self.assertEqual(fees["fee"], (9_500, 9_500))
        self.assertEqual(fees["creator_fee"], (3_000, 3_000))
        self.assertIn("cashback", fees)

    def test_no_fee_is_reproduced_on_an_exact_input_buy(self):
        """The fee there is taken from a gross input the event never states.

        Measured over all 20,803 exact-input buys: the protocol fee misses 103, creator_fee 20 and
        cashback 3, each by exactly one lamport. A near-miss is not a reproduction, so the gate
        returns nothing rather than certifying arithmetic it cannot do.
        """
        for name in B9I.EXACT_INPUT_BUYS:
            with self.subTest(ix_name=name):
                self.assertEqual(B9I.reproduce_fees(trade(ix_name=name)), {})

    def test_an_absent_basis_point_field_is_refused_never_defaulted(self):
        for bad in ({"fee_basis_points": None}, {"creator_fee": None},
                    {"cashback_fee_basis_points": "30"}):
            with self.subTest(bad=bad):
                with self.assertRaises(B9D.FreezeViolation) as ctx:
                    B9I.reproduce_fees(trade(**bad))
                self.assertIn("never defaulted", str(ctx.exception))


class RefusalGuardTests(unittest.TestCase):

    def test_a_bare_string_no_longer_passes_the_guard(self):
        """`set("buyback_fee")` iterates into CHARACTERS and intersects to nothing.

        The guard used to return quietly on exactly the call a caller is most likely to write,
        which is a refusal that fails open -- the worst kind.
        """
        for component in B9I.UNESTABLISHED_FEES:
            with self.subTest(component=component):
                with self.assertRaises(B9D.FreezeViolation) as ctx:
                    B9I.assert_unestablished_not_requested(component)
                self.assertIn("cannot be reproduced from pinned evidence", str(ctx.exception))
                with self.assertRaises(B9D.FreezeViolation):
                    B9I.assert_unestablished_not_requested([component])

    def test_every_declared_unestablished_name_is_actually_guarded(self):
        """The constant and the guard must share one vocabulary.

        They did not: the constant said "fee (exact-input buys only)" while the guard matched
        "fee_exact_input", so passing the module's own exported constant let that component through.
        """
        with self.assertRaises(B9D.FreezeViolation):
            B9I.assert_unestablished_not_requested(B9I.UNESTABLISHED_FEES)

    def test_established_components_are_allowed_through(self):
        self.assertTrue(B9I.assert_unestablished_not_requested(["fee", "creator_fee"]))
        self.assertTrue(B9I.assert_unestablished_not_requested(None))


if __name__ == "__main__":
    unittest.main()
