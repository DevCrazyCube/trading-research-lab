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

    def test_token_2022_extensions_decode_and_are_established_non_moving(self):
        """Established from the pinned source, not assumed.

        The token_metadata and metadata_pointer processors in spl-token-2022 11.0.0 contain no
        reference to lamports at all, so these are decoded and recorded as non-moving rather than
        being refused or silently skipped.
        """
        for tag, name in ((29, "Reallocate"), (39, "MetadataPointerExtension"),
                          (44, "PausableExtension")):
            with self.subTest(tag=tag):
                decoded = B9L.decode_token_instruction(bytes([tag]))
                self.assertEqual(decoded["name"], name)
                self.assertFalse(decoded["moves_lamports"])

    def test_withdraw_excess_lamports_refuses_loudly_rather_than_being_assumed_inert(self):
        """Tag 38 DOES move lamports -- processor.rs mutates source and destination balances -- and
        it never appears in the frozen artifact.

        Its amount is the balance above rent exemption and is not in the instruction data, so the
        first time one occurs it must stop the run rather than be attributed as zero.
        """
        self.assertIn(38, B9L.TOKEN_2022_LAMPORT_MOVING)
        with self.assertRaisesRegex(B9D.FreezeViolation, "WithdrawExcessLamports moves lamports"):
            B9L.decode_token_instruction(bytes([38]))

    def test_metadata_interface_discriminators_decode_by_their_eight_bytes(self):
        """These are routed by an 8-byte interface discriminator, not a one-byte enum tag.

        `d7e4a6e45464567b` is reproduced locally as
        sha256("spl_token_metadata_interface:update_the_authority")[:8], which is how the scheme
        was confirmed without trusting any single source.
        """
        import hashlib
        self.assertEqual(
            hashlib.sha256(b"spl_token_metadata_interface:update_the_authority").digest()[:8].hex(),
            "d7e4a6e45464567b")
        for discriminator, name in B9L.TOKEN_METADATA_INTERFACE.items():
            with self.subTest(name=name):
                decoded = B9L.decode_token_instruction(bytes.fromhex(discriminator) + b"\x00" * 4)
                self.assertEqual(decoded["name"], name)
                self.assertFalse(decoded["moves_lamports"])

    def test_a_discriminator_matching_nothing_pinned_is_refused(self):
        """Tag 45 and 255 match no SPL tag, no Token-2022 extension, and no interface
        discriminator. Assuming such an instruction moves no lamports is the silent under-count
        this work exists to prevent."""
        for tag in (45, 255):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(B9D.FreezeViolation, "matches no"):
                    B9L.decode_token_instruction(bytes([tag]) + b"\x00" * 8)

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
