"""B9p — the transaction we would construct, and the causal audit of residuals against it.

Two properties carry this module. Companion instructions must never be adopted as ours, because
adopting one imports a stranger's lamports as our cost. And a residual that nothing explains must
surface as a blocker, because the Phase 1 gate is "no unexplained cost divergence" -- an audit that
quietly resolves the unexplained defeats the gate it exists to serve.
"""
import importlib.util
import json
import pathlib
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9p_constructed_route", ROOT / "scripts" / "b9p_constructed_route.py")
B9P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9P)

B9D = B9P.B9D
IDLS = B9P.B9K.pinned_idls()
MAPS = B9P.idl_maps(IDLS)
PUMP_IDL = IDLS[B9D.PUMP_PROGRAM]


def pump_data(name):
    """Real discriminator bytes for a Pump instruction, from the pinned IDL."""
    entry = next(i for i in PUMP_IDL["instructions"] if i["name"] == name)
    return bytes(entry["discriminator"])


def envelope(program, data, inner_index=-1, accounts=()):
    return {"program_id": program, "data": data, "inner_index": inner_index,
            "outer_index": 0, "stack_height": 1 if inner_index == -1 else 2,
            "accounts": list(accounts)}


class RoleTests(unittest.TestCase):

    def test_a_pump_trade_is_part_of_our_constructed_transaction(self):
        for name in sorted(B9P.TRADE_INSTRUCTIONS):
            with self.subTest(name=name):
                role, label = B9P.outer_instruction_role(
                    envelope(B9D.PUMP_PROGRAM, pump_data(name)), MAPS)
                self.assertEqual(role, B9P.CONSTRUCTED)
                self.assertEqual(label, f"pump:{name}")

    def test_the_companions_this_artifact_actually_contains_are_not_ours(self):
        """Every one of these appears alongside trades in the frozen artifact, and every one moves
        lamports we would never move. `close_user_volume_accumulator` alone explains 91 residuals."""
        for name in ("close_user_volume_accumulator", "claim_cashback",
                     "sync_user_volume_accumulator", "collect_creator_fee_v2", "extend_account"):
            with self.subTest(name=name):
                role, label = B9P.outer_instruction_role(
                    envelope(B9D.PUMP_PROGRAM, pump_data(name)), MAPS)
                self.assertEqual(role, B9P.COMPANION, f"{name} must not be adopted as ours")

    def test_an_outer_token_transfer_is_a_companion_but_closing_our_account_is_not(self):
        transfer = B9P.outer_instruction_role(
            envelope(B9P.B9L.TOKEN_PROGRAM, bytes([3]) + b"\x00" * 8), MAPS)
        close = B9P.outer_instruction_role(
            envelope(B9P.B9L.TOKEN_PROGRAM, bytes([9])), MAPS)
        self.assertEqual(transfer[0], B9P.COMPANION)
        self.assertEqual(close[0], B9P.CONSTRUCTED)

    def test_an_unrecognised_program_defaults_to_companion(self):
        """The default must be COMPANION. Defaulting to constructed would silently adopt the
        lamport effects of anything this function has not been taught about."""
        role, _ = B9P.outer_instruction_role(envelope("SomeUnknownProgram1111", b"\x01"), MAPS)
        self.assertEqual(role, B9P.COMPANION)

    def test_pumpswap_is_never_part_of_our_route(self):
        """PumpSwap is not an initial entry venue (DECISIONS.md 2026-08-01)."""
        role, _ = B9P.outer_instruction_role(
            envelope(B9D.PUMPSWAP_PROGRAM, pump_data("buy")), MAPS)
        self.assertEqual(role, B9P.COMPANION)


class RouteShapeTests(unittest.TestCase):

    def trade(self):
        return envelope(B9D.PUMP_PROGRAM, pump_data("sell"))

    def companion(self):
        return envelope(B9D.PUMP_PROGRAM, pump_data("close_user_volume_accumulator"))

    def test_exactly_one_trade_is_our_shape(self):
        self.assertTrue(B9P.is_constructed_route([self.trade()], MAPS))
        self.assertTrue(B9P.is_constructed_route([self.trade(), self.companion()], MAPS))

    def test_a_transaction_with_no_trade_is_not_our_route(self):
        """The 11.115 SOL outlier: two creator-fee collections and no trade at all. It uses only
        pinned programs, so a program-only predicate admitted it, and its residual then dominated
        a trade-cost diagnostic by 18x."""
        self.assertFalse(B9P.is_constructed_route([self.companion()], MAPS))

    def test_two_trades_are_not_our_route_either(self):
        self.assertFalse(B9P.is_constructed_route([self.trade(), self.trade()], MAPS))

    def test_inner_instructions_do_not_count_as_outer_trades(self):
        """A trade reached by CPI from a router is not a trade WE submitted."""
        inner = envelope(B9D.PUMP_PROGRAM, pump_data("sell"), inner_index=0)
        self.assertFalse(B9P.is_constructed_route([inner], MAPS))


class AuditCaseTests(unittest.TestCase):
    """The decision logic, with the two measurements stubbed so every branch is reachable."""

    def stub(self, residual, credit, shaped=True):
        self.addCleanup(setattr, B9P.B9K, "reconcile_transaction",
                        B9P.B9K.reconcile_transaction)
        self.addCleanup(setattr, B9P, "accumulator_closure_credit",
                        B9P.accumulator_closure_credit)
        self.addCleanup(setattr, B9P, "is_constructed_route", B9P.is_constructed_route)
        self.addCleanup(setattr, B9D, "envelope_instructions", B9D.envelope_instructions)
        B9P.B9K.reconcile_transaction = lambda *a, **k: {"residual": residual}
        B9P.accumulator_closure_credit = lambda *a, **k: credit
        B9P.is_constructed_route = lambda *a, **k: shaped
        B9D.envelope_instructions = lambda *a, **k: []
        return B9P.audit_residual(object(), IDLS, MAPS)

    def test_an_exactly_matching_companion_credit_is_case_a(self):
        self.assertEqual(self.stub(-1_844_400, 1_844_400)["case"], B9P.CASE_A_OUTSIDE_ROUTE)

    def test_a_near_miss_is_never_case_a(self):
        """One lamport out is not explained. Accepting it would be inventing the tolerance this
        project refuses everywhere else."""
        self.assertEqual(self.stub(-1_844_401, 1_844_400)["case"], B9P.CASE_B_IN_TRADE_SUBTREE)

    def test_an_unexplained_residual_in_our_shape_is_a_blocker(self):
        self.assertEqual(self.stub(-5_000, 0)["case"], B9P.CASE_B_IN_TRADE_SUBTREE)

    def test_an_unexplained_residual_outside_our_shape_is_not_a_blocker(self):
        self.assertEqual(self.stub(-5_000, 0, shaped=False)["case"], B9P.CASE_C_INSUFFICIENT)

    def test_the_cases_are_mutually_exclusive_and_named(self):
        for residual, credit, shaped in ((-10, 10, True), (-10, 0, True), (-10, 0, False)):
            with self.subTest(residual=residual, credit=credit, shaped=shaped):
                self.assertIn(self.stub(residual, credit, shaped)["case"], B9P.AUDIT_CASES)


class ExhaustivenessTests(unittest.TestCase):

    def test_the_close_accumulator_account_role_matches_the_pinned_idl(self):
        """accounts[1] is the account being closed. Reading the wrong index would attribute some
        other account's balance and still produce a plausible number."""
        entry = next(i for i in PUMP_IDL["instructions"]
                     if i["name"] == B9P.CLOSE_ACCUMULATOR)
        self.assertEqual(entry["accounts"][B9P.CLOSE_ACCUMULATOR_TARGET]["name"],
                         "user_volume_accumulator")
        self.assertTrue(entry["accounts"][B9P.CLOSE_ACCUMULATOR_TARGET]["writable"])
        self.assertEqual(entry["accounts"][0]["name"], "user")

    def synthetic(self, pre_balance, system_credit=None, cashback=None):
        """One close_user_volume_accumulator, optionally funded in the same transaction."""
        accumulator, payer = "accumulator", "payer"
        envelopes = [{"program_id": B9D.PUMP_PROGRAM,
                      "data": pump_data(B9P.CLOSE_ACCUMULATOR),
                      "accounts": [payer, accumulator],
                      "inner_index": -1, "outer_index": 0, "stack_height": 1}]
        if system_credit is not None:
            import struct
            envelopes.append({
                "program_id": B9P.SYSTEM_PROGRAM,
                "data": struct.pack("<I", 2) + struct.pack("<Q", system_credit),
                "accounts": [payer, accumulator],
                "inner_index": 0, "outer_index": 0, "stack_height": 2})
        for attribute, value in (("envelope_instructions", lambda *a, **k: envelopes),
                                 ("resolve_account_keys", lambda *a, **k: [payer, accumulator]),
                                 ("parse_message", lambda *a, **k: {})):
            self.addCleanup(setattr, B9D, attribute, getattr(B9D, attribute))
            setattr(B9D, attribute, value)
        if cashback is not None:
            envelopes.append({"program_id": B9D.PUMP_PROGRAM, "data": b"EVENT",
                              "accounts": [], "inner_index": 1, "outer_index": 0,
                              "stack_height": 2})
            saved = B9D.decode_anchor_cpi_event
            self.addCleanup(setattr, B9D, "decode_anchor_cpi_event", saved)
            B9D.decode_anchor_cpi_event = lambda p, d, i: (
                {"name": "TradeEvent", "fields": {"cashback": cashback}}
                if d == b"EVENT" else None)
        result = {"meta": {"preBalances": [0, pre_balance]}, "transaction": ["", "base64"]}
        return B9P.accumulator_closure_credit(result, IDLS, MAPS)

    def test_the_credit_is_the_balance_at_close_not_the_pre_balance(self):
        """An accumulator CREATED and closed in the same transaction has pre-balance zero and still
        refunds full rent. 32 of the 92 residuals are exactly this shape, and reading the
        pre-balance reports zero credit for every one of them -- the same trap that made
        `CloseAccount` rent wrong when it was first read from pre-balances.
        """
        self.assertEqual(self.synthetic(pre_balance=0, system_credit=1_844_400), 1_844_400)
        self.assertEqual(self.synthetic(pre_balance=1_844_400), 1_844_400)

    def test_cashback_arriving_by_system_transfer_is_not_counted_twice(self):
        """Observed on 3 of the 92: the cashback shows up both as a decoded System credit and as
        the TradeEvent field. Adding both overstates the credit and breaks the exact match."""
        self.assertEqual(
            self.synthetic(pre_balance=1_844_400, system_credit=4_163, cashback=4_163),
            1_844_400 + 4_163)

    def test_cashback_paid_directly_by_pump_is_counted_once(self):
        self.assertEqual(
            self.synthetic(pre_balance=1_844_400, cashback=4_163), 1_844_400 + 4_163)

    def test_a_harvested_pumpswap_creator_fee_is_a_companion_credit(self):
        """The 11.115 SOL outlier reconciles to the lamport against this event's stated amount.

        We never collect creator fees -- we are not the creator of tokens we trade, and PumpSwap is
        not an entry venue -- so the whole amount is outside our route.
        """
        envelopes = [{"program_id": B9D.PUMPSWAP_PROGRAM, "data": b"EVT", "accounts": [],
                      "inner_index": 0, "outer_index": 0, "stack_height": 2}]
        self.addCleanup(setattr, B9D, "envelope_instructions", B9D.envelope_instructions)
        self.addCleanup(setattr, B9D, "decode_anchor_cpi_event", B9D.decode_anchor_cpi_event)
        B9D.envelope_instructions = lambda *a, **k: envelopes
        B9D.decode_anchor_cpi_event = lambda p, d, i: (
            {"name": B9P.COIN_CREATOR_FEE_EVENT,
             "fields": {B9P.COIN_CREATOR_FEE_FIELD: 11_115_209_190}} if d == b"EVT" else None)
        self.assertEqual(B9P.coin_creator_fee_credit({}, IDLS), 11_115_209_190)

    def test_no_close_instruction_means_no_companion_credit(self):
        for attribute, value in (("envelope_instructions", lambda *a, **k: []),
                                 ("resolve_account_keys", lambda *a, **k: ["payer"]),
                                 ("parse_message", lambda *a, **k: {})):
            self.addCleanup(setattr, B9D, attribute, getattr(B9D, attribute))
            setattr(B9D, attribute, value)
        self.assertEqual(B9P.accumulator_closure_credit(
            {"meta": {"preBalances": [0]}, "transaction": ["", "base64"]}, IDLS, MAPS), 0)

    def test_a_close_instruction_with_too_few_accounts_is_refused(self):
        saved = B9D.envelope_instructions
        self.addCleanup(setattr, B9D, "envelope_instructions", saved)
        B9D.envelope_instructions = lambda *a, **k: [
            {"program_id": B9D.PUMP_PROGRAM, "data": pump_data(B9P.CLOSE_ACCUMULATOR),
             "accounts": ["only-one"], "inner_index": -1, "outer_index": 0, "stack_height": 1}]
        saved_keys = B9D.resolve_account_keys
        self.addCleanup(setattr, B9D, "resolve_account_keys", saved_keys)
        B9D.resolve_account_keys = lambda *a, **k: ["payer"]
        saved_parse = B9D.parse_message
        self.addCleanup(setattr, B9D, "parse_message", saved_parse)
        B9D.parse_message = lambda *a, **k: {}
        result = {"meta": {"preBalances": [1]}, "transaction": ["", "base64"]}
        with self.assertRaisesRegex(B9D.FreezeViolation, "user_volume_accumulator"):
            B9P.accumulator_closure_credit(result, IDLS, MAPS)


if __name__ == "__main__":
    unittest.main()
