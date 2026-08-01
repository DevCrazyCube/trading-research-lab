"""B9l SPL Token instruction decoding against the pinned ABI.

`CloseAccount` is the only pinned variant that moves lamports, so it carries most of these tests.
"""
import importlib.util
import pathlib
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9l_token_instructions", ROOT / "scripts" / "b9l_token_instructions.py")
B9L = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9L)

B9D = B9DT.B9D
B9L.B9D = B9D
B9L.FreezeViolation = B9D.FreezeViolation


class PinTests(unittest.TestCase):

    def test_the_vendored_abi_still_hashes_to_its_pin(self):
        self.assertTrue(B9L.assert_abi_source_pinned())

    def test_a_drifted_abi_source_is_refused(self):
        saved = B9L.TOKEN_ABI_SOURCE_SHA256
        B9L.TOKEN_ABI_SOURCE_SHA256 = "0" * 64
        self.addCleanup(lambda: setattr(B9L, "TOKEN_ABI_SOURCE_SHA256", saved))
        with self.assertRaisesRegex(B9D.FreezeViolation, "stated against the pinned revision"):
            B9L.assert_abi_source_pinned()

    def test_the_discriminator_is_one_byte_not_four(self):
        """Unlike the System program. Reading four bytes here would decode every instruction wrong."""
        self.assertEqual(B9L.decode_token_instruction(bytes([12, 0, 0, 0]))["name"],
                         "TransferChecked")
        self.assertEqual(B9L.decode_token_instruction(bytes([9]))["name"], "CloseAccount")

    def test_close_account_is_the_only_pinned_variant_that_moves_lamports(self):
        """If this stops being true, the reconciliation silently under-attributes."""
        movers = [tag for tag in B9L.TOKEN_INSTRUCTIONS
                  if B9L.decode_token_instruction(bytes([tag]))["moves_lamports"]]
        self.assertEqual(movers, [B9L.CLOSE_ACCOUNT])
        self.assertEqual(B9L.TOKEN_INSTRUCTIONS[9], "CloseAccount")


class RefusalTests(unittest.TestCase):

    def test_token_2022_extension_discriminators_are_refused(self):
        """Observed in the artifact: tags 45 and 210. They are above the pinned range.

        Refusing them is the point. Assuming an unpinned extension moves no lamports is exactly
        the silent under-count this work exists to prevent.
        """
        for tag in (25, 45, 210, 255):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(B9D.FreezeViolation, "outside the pinned SPL Token"):
                    B9L.decode_token_instruction(bytes([tag]))

    def test_empty_data_is_refused(self):
        with self.assertRaisesRegex(B9D.FreezeViolation, "no discriminator"):
            B9L.decode_token_instruction(b"")


class CloseAccountMovementTests(unittest.TestCase):

    def envelope(self, accounts):
        return {"accounts": accounts, "data": bytes([9]), "outer_index": 0, "inner_index": 0}

    def test_the_closed_account_balance_goes_to_the_destination(self):
        keys = ["closed", "destination", "owner"]
        source, destination, lamports = B9L.close_account_movement(
            self.envelope(keys), keys, [2_039_280, 0, 5])
        self.assertEqual((source, destination, lamports), ("closed", "destination", 2_039_280))

    def test_too_few_accounts_is_refused(self):
        with self.assertRaisesRegex(B9D.FreezeViolation, "closed account and a destination"):
            B9L.close_account_movement(self.envelope(["only"]), ["only"], [1])

    def test_an_ambiguous_closed_account_is_refused(self):
        """An attribution that cannot identify its own account is worse than none."""
        keys = ["dup", "dup", "owner"]
        with self.assertRaisesRegex(B9D.FreezeViolation, "its balance is ambiguous"):
            B9L.close_account_movement(self.envelope(["dup", "other", "owner"]), keys, [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
