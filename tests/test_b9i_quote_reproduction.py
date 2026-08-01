import importlib.util
import json
import pathlib
import tempfile
import unittest

import tests.test_b9d_transaction_bodies as B9DT


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
        """The bare-string guard is the point here: `set("fee_exact_input")` iterates into
        characters and would fail OPEN on exactly the call a caller is most likely to write."""
        with self.assertRaisesRegex(B9I.FreezeViolation, "cannot be reproduced"):
            B9I.assert_unestablished_not_requested("fee_exact_input")
        with self.assertRaisesRegex(B9I.FreezeViolation, "cannot be reproduced"):
            B9I.assert_unestablished_not_requested(["fee_exact_input"])
        self.assertTrue(B9I.assert_unestablished_not_requested(["fee", "creator_fee"]))

    def test_the_buyback_fee_is_no_longer_unestablished(self):
        """Resolved 2026-08-01. It must now reproduce rather than refuse."""
        self.assertNotIn("buyback_fee", B9I.UNESTABLISHED_FEES)
        self.assertTrue(B9I.assert_unestablished_not_requested(["buyback_fee"]))


class BuybackFeeTests(unittest.TestCase):
    """`floor(fee * bps / 10000)` -- exact on 93,448/93,448 across the full population."""

    def fields(self, fee, bps=5000, observed=None):
        return {"fee": fee, "buyback_fee_basis_points": bps,
                "buyback_fee": fee * bps // 10000 if observed is None else observed}

    def test_the_rounding_is_floor_and_not_ceil(self):
        """This is the whole finding. At 5,000 bps an ODD fee is where the two disagree, and
        `ceil` matching ~half the population was the signature of the wrong mode -- it read as an
        unidentified base for two handoffs."""
        predicted, observed = B9I.reproduce_buyback_fee(self.fields(101))
        self.assertEqual((predicted, observed), (50, 50))
        self.assertEqual(B9I.ceil_div(101 * 5000, 10000), 51)

    def test_an_even_fee_cannot_tell_the_two_roundings_apart(self):
        """So a fixture with an even fee would let a `ceil` mutant survive."""
        self.assertEqual(B9I.reproduce_buyback_fee(self.fields(100))[0],
                         B9I.ceil_div(100 * 5000, 10000))

    def test_a_missing_or_negative_field_is_refused_rather_than_defaulted(self):
        for broken in ({"fee": None}, {"buyback_fee_basis_points": None},
                       {"fee": -1}, {"buyback_fee": True}):
            with self.subTest(broken=broken):
                with self.assertRaisesRegex(B9I.FreezeViolation, "never defaulted"):
                    B9I.reproduce_buyback_fee(dict(self.fields(101), **broken))

    def test_a_rate_outside_the_basis_point_range_is_refused(self):
        with self.assertRaisesRegex(B9I.FreezeViolation, "outside 0..10000"):
            B9I.reproduce_buyback_fee(self.fields(101, bps=10_001))

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

    def test_exact_input_fees_reproduce_from_the_decoded_gross_input(self):
        """The base is the fee-inclusive net of the GROSS, not the quote that reaches reserves.

        Reproducing from the quote is short by exactly one lamport on about 0.5% of exact-input
        buys, which is why these three were unestablished until the parent instruction's own
        pinned `spendable_*` argument made the gross decodable.
        """
        fields = {"ix_name": "buy_exact_sol_in", "is_buy": True,
                  "quote_amount": 987_902, "token_amount": 1,
                  "fee_basis_points": 95, "fee": 9_405,
                  "creator_fee_basis_points": 30, "creator_fee": 2_970,
                  "cashback_fee_basis_points": 0, "cashback": 0}
        gross = 1_000_277
        net = gross * 10000 // (10000 + 95 + 30 + 0)
        self.assertEqual(B9I.reproduce_exact_input_fees(gross, fields)["fee"],
                         (-(-net * 95 // 10000), 9_405))
        self.assertEqual(gross, fields["quote_amount"] + fields["fee"]
                         + fields["creator_fee"] + fields["cashback"],
                         "the gross must decompose exactly, or it is not the number the program split")

    def test_the_gross_input_comes_from_the_pinned_argument_or_not_at_all(self):
        """A gross that cannot be decoded exactly must never be approximated: it is the base of
        three fees, so a wrong base is a wrong fee that still looks like a reproduction."""
        pump = B9I.B9D.load_pinned_idl(
            B9I.B9D.PUMP_IDL_PATH, B9I.B9D.PUMP_IDL_SHA256, B9I.B9D.PUMP_PROGRAM)
        argument_map = B9I.pinned_instruction_arguments(pump)
        discriminator = next(k for k, v in argument_map.items() if v[0] == "buy_exact_sol_in")
        data = bytes.fromhex(discriminator) + (1_000_277).to_bytes(8, "little")
        self.assertEqual(B9I.decode_gross_input(data, argument_map), 1_000_277)

        # A non-exact-input parent is not an error; it is how the caller learns it does not apply.
        legacy = next(k for k, v in argument_map.items() if v[0] == "buy")
        self.assertIsNone(B9I.decode_gross_input(
            bytes.fromhex(legacy) + b"\x00" * 8, argument_map))

        with self.assertRaisesRegex(B9I.FreezeViolation, "absent from the pinned IDL"):
            B9I.decode_gross_input(b"\xff" * 16, argument_map)
        with self.assertRaisesRegex(B9I.FreezeViolation, "too short"):
            B9I.decode_gross_input(bytes.fromhex(discriminator) + b"\x00", argument_map)

    def test_a_parent_whose_pinned_argument_moved_is_refused(self):
        """The layout is only evidence while it matches the pin.

        If a revision renames or retypes the first argument, reading eight bytes at offset 8 would
        still return a plausible integer -- and a wrong gross is a wrong fee that still looks like
        a reproduction.
        """
        pump = B9I.B9D.load_pinned_idl(
            B9I.B9D.PUMP_IDL_PATH, B9I.B9D.PUMP_IDL_SHA256, B9I.B9D.PUMP_PROGRAM)
        argument_map = B9I.pinned_instruction_arguments(pump)
        discriminator = next(k for k, v in argument_map.items() if v[0] == "buy_exact_sol_in")
        data = bytes.fromhex(discriminator) + (1_000_277).to_bytes(8, "little")
        for drifted in (("buy_exact_sol_in", "renamed_input", "u64"),
                        ("buy_exact_sol_in", "spendable_sol_in", "u128")):
            with self.subTest(drifted=drifted):
                doctored = dict(argument_map, **{discriminator: drifted})
                with self.assertRaisesRegex(B9I.FreezeViolation, "gross input is not where it was"):
                    B9I.decode_gross_input(data, doctored)

    def test_the_gross_decomposition_is_reported_not_required(self):
        """It holds on 20,800 of 20,803, and the three exceptions leave exactly one lamport whose
        destination is not in evidence.

        Requiring it would fail an artifact whose quotes and fees all reproduce exactly; tolerating
        a residue of "1" would be inventing a tolerance to fit the observation. So the gate reports
        it, and a caller who wants it enforced asks explicitly and states its own bound.
        """
        report = {"observations": 10, "quote_mismatch": 0, "fees": {},
                  "gross_input": {"n": 4, "identity_exact": 3, "residues": {"1": 1},
                                  "first_residue": {"residue": 1}}}
        saved = B9I.reproduce_artifact
        B9I.reproduce_artifact = lambda *a, **k: report
        self.addCleanup(lambda: setattr(B9I, "reproduce_artifact", saved))
        self.assertTrue(B9I.assert_quote_reproduction(None)["exact"],
                        "a one-lamport residue must not fail the quote/fee gate")

        with self.assertRaisesRegex(B9I.FreezeViolation, "residues beyond 0"):
            B9I.assert_gross_identity_residue(report)
        self.assertTrue(B9I.assert_gross_identity_residue(report, maximum=1))

    def test_nonpositive_legacy_denominator_fails_closed(self):
        fields = {"ix_name": "buy", "is_buy": True, "token_amount": 10, "quote_amount": 1}
        with self.assertRaisesRegex(B9I.FreezeViolation, "whole virtual token reserve"):
            B9I.reproduce_trade(20, 10, fields)


class ReproduceArtifactLoopTests(unittest.TestCase):
    """The loop, not just the functions.

    Unit tests over reproduce_exact_input_fees left a mutant alive that simply never called it and
    fell back to the quote base -- the loop is where the choice is made, so the loop is where it
    has to be held.
    """

    def setUp(self):
        self.b9d = B9DT.B9D
        B9I.B9D = self.b9d
        B9I.FreezeViolation = self.b9d.FreezeViolation
        self.path = pathlib.Path(tempfile.mkdtemp()) / "repro.sqlite"
        self.database = self.b9d.connect(str(self.path))
        self.b9d.schema(self.database)
        self.addCleanup(self.database.close)

    def build(self, gross, quote, fee, creator, buyback_bps=0, buyback=0):
        """One exact-input buy whose fees reconcile ONLY against the gross-derived base."""
        idl = self.b9d.load_pinned_idl(
            self.b9d.PUMP_IDL_PATH, self.b9d.PUMP_IDL_SHA256, self.b9d.PUMP_PROGRAM)
        buy = next(i for i in idl["instructions"] if i["name"] == "buy_exact_sol_in")
        parent = bytes(buy["discriminator"]) + gross.to_bytes(8, "little") + b"\x00" * 8
        event = B9DT.encode_pump_event(
            "TradeEvent", mint="So11111111111111111111111111111111111111112", is_buy=True,
            quote_amount=quote, token_amount=1, quote_mint=self.b9d.NATIVE_QUOTE_MINT,
            ix_name="buy_exact_sol_in", fee_basis_points=95, fee=fee,
            creator_fee_basis_points=30, creator_fee=creator,
            cashback_fee_basis_points=0, cashback=0,
            buyback_fee_basis_points=buyback_bps, buyback_fee=buyback,
            virtual_quote_reserves=30_000_000_000, virtual_token_reserves=1_073_000_000_000_000,
            real_quote_reserves=0, real_token_reserves=0)
        keys = [self.b9d.base58_decode(self.b9d.PUMP_PROGRAM), bytes(range(32))]
        meta = {"innerInstructions": [{"index": 0, "instructions": [
            {"programIdIndex": 0, "accounts": [], "data": self.b9d.base58(event),
             "stackHeight": 2}]}]}
        raw = json.dumps({"result": B9DT.as_result(
            B9DT.build_transaction(keys, [(0, [1], parent)]), meta=meta, slot=700)}).encode()
        with self.database:
            self.database.execute(
                "INSERT INTO raw_transaction (signature,method,params_json,received_at_unix,"
                "response_sha256,raw_zlib) VALUES ('sig','m','[]',1.0,?,?)",
                (self.b9d.hashlib.sha256(raw).hexdigest(), self.b9d.zlib.compress(raw, 6)))
            self.database.execute("INSERT INTO transaction_coordinate VALUES ('sig',700,0)")
            self.database.execute(
                "INSERT INTO reserve_observation (slot,transaction_index,outer_index,inner_index,"
                "bonding_curve,virtual_quote_before,virtual_token_before,real_quote_before,"
                "real_token_before,virtual_quote_after,virtual_token_after,real_quote_after,"
                "real_token_after,evidence) VALUES (700,0,0,-1,'curve',?,?,0,0,0,0,0,0,?)",
                (30_000_000_000, 1_073_000_000_000_000,
                 json.dumps({"kind": "anchor_cpi:TradeEvent",
                             "event_outer_index": 0, "event_inner_index": 0})))

    def test_the_buyback_fee_is_reproduced_by_the_loop_with_floor(self):
        """The loop, not just the function -- a mutant that never calls it survives unit tests.

        The fixture's fee is deliberately ODD: at 5,000 bps floor and ceil differ only there, so an
        even fee would let a `ceil` mutant through the very test written to catch it.
        """
        gross = 100_000  # yields fee 939 -- odd, so floor 469 != ceil 470
        net = gross * 10000 // (10000 + 95 + 30)
        fee, creator = -(-net * 95 // 10000), -(-net * 30 // 10000)
        self.assertEqual(fee % 2, 1, "fixture must use an odd fee or it cannot discriminate")
        self.build(gross, gross - fee - creator, fee, creator,
                   buyback_bps=5000, buyback=fee * 5000 // 10000)
        bucket = B9I.reproduce_artifact(self.database)["fees"]["buyback_fee"]
        self.assertEqual((bucket["exact"], bucket["n"]), (1, 1))

    def test_the_loop_actually_predicts_the_buyback_rather_than_echoing_it(self):
        """A loop that sets predicted = observed reports 1/1 and looks perfect.

        Mutation found exactly that mutant alive against the agreeing-fixture test above, which is
        the same way the gross-input reproduction was once faked. The only fixture that can tell
        the two apart is one whose OBSERVED buyback is wrong: a real prediction disagrees and
        reports 0/1, an echo agrees with itself and reports 1/1.
        """
        gross = 100_000
        net = gross * 10000 // (10000 + 95 + 30)
        fee, creator = -(-net * 95 // 10000), -(-net * 30 // 10000)
        self.build(gross, gross - fee - creator, fee, creator,
                   buyback_bps=5000, buyback=fee * 5000 // 10000 + 7)
        bucket = B9I.reproduce_artifact(self.database)["fees"]["buyback_fee"]
        self.assertEqual((bucket["exact"], bucket["n"]), (0, 1))

    def test_the_report_separates_what_was_offered_from_what_was_debited(self):
        """`spendable_*` is a CAP, so gross offered and lamports debited are different quantities.

        Where the fee-inclusive division leaves a remainder the program does not spend it: on all
        three residue observations in the frozen artifact no account moves by one lamport, and the
        payer's debit decomposes into quote + fees + rent + transaction fee with the gross playing
        no part. Reporting only the gross would overstate the user's cost.
        """
        gross = 100_079
        net = gross * 10000 // (10000 + 95 + 30)
        fee, creator = -(-net * 95 // 10000), -(-net * 30 // 10000)
        quote = gross - fee - creator
        self.build(gross, quote, fee, creator)
        report = B9I.reproduce_artifact(self.database)
        bucket = report["gross_input"]["by_quote_mint"][self.b9d.NATIVE_QUOTE_MINT]
        debit = bucket["protocol_debit_raw_quote"]
        self.assertEqual(debit, quote + fee + creator)
        self.assertEqual(bucket["gross_offered_raw_quote"], gross)
        self.assertEqual(bucket["n"], 1)
        self.assertGreaterEqual(gross, debit, "the cap can never be less than what was debited")

    def test_an_exact_input_event_without_a_quote_mint_fails_closed(self):
        """Units are only lamports for the native mint, so an unknown mint means unknown units.

        Silently bucketing it would put SPL raw units and lamports in one total -- a number that
        looks plausible and means nothing. Guarded, but untested until a mutation showed the
        refusal could be deleted without any test noticing.
        """
        gross = 100_079
        net = gross * 10000 // (10000 + 95 + 30)
        fee, creator = -(-net * 95 // 10000), -(-net * 30 // 10000)
        self.build(gross, gross - fee - creator, fee, creator)
        real = self.b9d.decode_anchor_cpi_event

        def stripped(program_id, data, idls):
            decoded = real(program_id, data, idls)
            if decoded and decoded["name"] == "TradeEvent":
                decoded["fields"].pop("quote_mint", None)
            return decoded

        self.b9d.decode_anchor_cpi_event = stripped
        self.addCleanup(lambda: setattr(self.b9d, "decode_anchor_cpi_event", real))
        with self.assertRaisesRegex(B9I.FreezeViolation, "no quote_mint"):
            B9I.reproduce_artifact(self.database)

    def test_exact_input_fees_are_reproduced_from_the_gross_by_the_loop(self):
        """These fees do NOT reconcile against the quote base, so a loop that fell back to it
        would report a mismatch. Only the gross-derived net reproduces them."""
        # Chosen so the two bases DISAGREE: the quote base gives 939, the gross-derived net
        # gives 940. Most grosses cannot tell the two apart, which is exactly why the +1 lamport
        # discrepancy looked like noise until the gross was decodable.
        gross = 100_079
        net = gross * 10000 // (10000 + 95 + 30)
        fee, creator = -(-net * 95 // 10000), -(-net * 30 // 10000)
        quote = gross - fee - creator
        self.build(gross, quote, fee, creator)
        report = B9I.reproduce_artifact(self.database)
        self.assertEqual(report["observations"], 1)
        self.assertEqual((report["gross_input"]["n"], report["gross_input"]["identity_exact"]),
                         (1, 1))
        self.assertEqual(report["fees"]["fee"]["exact"], 1)
        self.assertEqual(report["fees"]["creator_fee"]["exact"], 1)
        self.assertNotEqual(fee, -(-quote * 95 // 10000),
                            "fixture is pointless unless the quote base gives a DIFFERENT fee")


if __name__ == "__main__":
    unittest.main()
