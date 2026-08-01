"""B9k transaction-level wallet-cost reconciliation.

The value is in the categorisation: what is exactly attributed, and what is visibly not.
"""
import base64
import importlib.util
import json
import pathlib
import struct
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9k_wallet_cost", ROOT / "scripts" / "b9k_wallet_cost.py")
B9K = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9K)

B9D = B9DT.B9D
B9K.B9D = B9D
B9K.B9J.B9D = B9D
B9K.FreezeViolation = B9D.FreezeViolation
B9K.B9J.FreezeViolation = B9D.FreezeViolation

SYSTEM = B9K.B9J.SYSTEM_PROGRAM


def system_transfer(lamports):
    return struct.pack("<I", 2) + struct.pack("<Q", lamports)


class ReconcileTests(unittest.TestCase):
    """Built directly, so the identity is exercised rather than a fixture's arithmetic."""

    def result(self, instructions, pre, post, fee, keys=None):
        keys = keys or [B9D.base58_decode(SYSTEM), bytes(range(32)), bytes(range(1, 33))]
        raw = B9DT.build_transaction(keys, instructions)
        result = B9DT.as_result(raw, meta={"preBalances": pre, "postBalances": post}, slot=700)
        result["meta"]["fee"] = fee
        return result

    def test_a_transaction_whose_movements_are_all_system_reconciles_exactly(self):
        """payer_debit == fee + sent - received, to the lamport."""
        # keys[0] is the System program itself in this fixture's layout, so the payer is index 0 of
        # the resolved keys -- build the transfer as account 0 -> account 1.
        keys = [bytes(range(32)), bytes(range(1, 33)), B9D.base58_decode(SYSTEM)]
        raw = B9DT.build_transaction(keys, [(2, [0, 1], system_transfer(500))])
        result = B9DT.as_result(
            raw, meta={"preBalances": [10_000, 0, 1], "postBalances": [9_400, 500, 1]}, slot=700)
        result["meta"]["fee"] = 100
        record = B9K.reconcile_transaction(result)
        self.assertEqual(record["category"], "exact")
        self.assertEqual((record["payer_debit"], record["system_sent"], record["residual"]),
                         (600, 500, 0))

    def test_lamports_the_payer_receives_reduce_the_attributed_cost(self):
        """Cost is net. A payer that is refunded within the transaction paid less, and a
        reconciliation that only counted outflows would overstate every such trade."""
        keys = [bytes(range(32)), bytes(range(1, 33)), B9D.base58_decode(SYSTEM)]
        raw = B9DT.build_transaction(keys, [(2, [1, 0], system_transfer(700))])
        result = B9DT.as_result(
            raw, meta={"preBalances": [10_000, 700, 1], "postBalances": [10_600, 0, 1]}, slot=700)
        result["meta"]["fee"] = 100
        record = B9K.reconcile_transaction(result)
        self.assertEqual(record["category"], "exact")
        self.assertEqual((record["system_received"], record["system_sent"]), (700, 0))
        self.assertEqual(record["payer_debit"], -600, "a net credit is a negative debit")
        self.assertEqual(record["residual"], 0)

    def test_a_movement_no_system_instruction_explains_is_visibly_unattributed(self):
        """The limit this gate exists to make visible.

        A program may move lamports on accounts it owns with no System instruction -- SPL Token
        `CloseAccount` returning rent is the common case. That is not reconciled and must never be
        absorbed; it is categorised, with the accounts carrying it named.
        """
        keys = [bytes(range(32)), bytes(range(1, 33)), B9D.base58_decode(SYSTEM)]
        raw = B9DT.build_transaction(keys, [(2, [0, 1], system_transfer(500))])
        # Account 1 also returns 2,039,280 to the payer with nothing decodable saying so.
        result = B9DT.as_result(
            raw, meta={"preBalances": [10_000, 2_039_280, 1],
                       "postBalances": [9_400 + 2_039_280, 500, 1]}, slot=700)
        result["meta"]["fee"] = 100
        record = B9K.reconcile_transaction(result)
        self.assertEqual(record["category"], "unattributed_movement")
        self.assertEqual(record["residual"], -2_039_280)
        self.assertTrue(record["carriers"], "the accounts carrying it must be named")

    def test_an_undecodable_system_instruction_categorises_the_whole_transaction(self):
        """One transaction in the frozen artifact carries two of these. It must be named, not
        crashed on and not skipped."""
        keys = [bytes(range(32)), bytes(range(1, 33)), B9D.base58_decode(SYSTEM)]
        padded = struct.pack("<I", 0) + struct.pack("<QQ", 1, 165) + bytes(32) + bytes(4)
        raw = B9DT.build_transaction(keys, [(2, [0, 1], padded)])
        result = B9DT.as_result(
            raw, meta={"preBalances": [10_000, 0, 1], "postBalances": [9_900, 0, 1]}, slot=700)
        result["meta"]["fee"] = 100
        record = B9K.reconcile_transaction(result)
        self.assertEqual(record["category"], "undecodable_system")
        self.assertIn("trailing byte", record["undecodable"][0]["reason"])

    def test_a_missing_or_invalid_fee_is_refused(self):
        keys = [bytes(range(32)), bytes(range(1, 33)), B9D.base58_decode(SYSTEM)]
        raw = B9DT.build_transaction(keys, [(2, [0, 1], system_transfer(1))])
        for fee in (None, -1, "100"):
            with self.subTest(fee=fee):
                result = B9DT.as_result(
                    raw, meta={"preBalances": [1, 1, 1], "postBalances": [1, 1, 1]}, slot=700)
                result["meta"]["fee"] = fee
                with self.assertRaisesRegex(B9D.FreezeViolation, "transaction fee"):
                    B9K.reconcile_transaction(result)

    def test_balance_vectors_must_match_the_resolved_keys(self):
        keys = [bytes(range(32)), bytes(range(1, 33)), B9D.base58_decode(SYSTEM)]
        raw = B9DT.build_transaction(keys, [(2, [0, 1], system_transfer(1))])
        result = B9DT.as_result(raw, meta={"preBalances": [1], "postBalances": [1]}, slot=700)
        result["meta"]["fee"] = 0
        with self.assertRaisesRegex(B9D.FreezeViolation, "resolved account keys"):
            B9K.reconcile_transaction(result)

    def test_the_module_shares_one_freeze_violation_class_with_its_decoder(self):
        """Loading b9d twice yields two distinct FreezeViolation classes.

        `except FreezeViolation` in b9k would then not catch what b9j raises, so the
        undecodable-instruction handler would never fire and a full run would die on the one
        transaction it exists to categorise. It did. This test file rebinds both modules to a
        single instance, which MASKED the defect -- so the identity is asserted on the modules as
        imported, not as this file has arranged them.
        """
        fresh_spec = importlib.util.spec_from_file_location(
            "b9k_fresh", ROOT / "scripts" / "b9k_wallet_cost.py")
        fresh = importlib.util.module_from_spec(fresh_spec)
        fresh_spec.loader.exec_module(fresh)
        self.assertIs(fresh.FreezeViolation, fresh.B9J.FreezeViolation)
        self.assertIs(fresh.B9D, fresh.B9J.B9D)

    def test_categories_are_exhaustive(self):
        """Every transaction lands in exactly one bucket, so a coverage fraction means something."""
        self.assertEqual(set(B9K.CATEGORIES),
                         {"exact", "undecodable_system", "unattributed_movement"})


if __name__ == "__main__":
    unittest.main()
