"""B9j System instruction decoding against the pinned ABI.

The decoder's value is entirely in what it refuses, so most of these tests are refusals.
"""
import importlib.util
import pathlib
import struct
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9j_system_instructions", ROOT / "scripts" / "b9j_system_instructions.py")
B9J = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9J)

B9D = B9DT.B9D
B9J.B9D = B9D
B9J.FreezeViolation = B9D.FreezeViolation

PUBKEY = bytes(range(32))


def encode(tag, payload=b""):
    return struct.pack("<I", tag) + payload


class PinTests(unittest.TestCase):

    def test_the_vendored_abi_still_hashes_to_its_pin(self):
        """The layout table is stated against one revision; applying it to another is not evidence."""
        self.assertTrue(B9J.assert_abi_source_pinned())

    def test_a_drifted_abi_source_is_refused(self):
        """Asserting the pin passes is not the same as asserting it CAN fail.

        The happy-path check returns True whether or not the comparison happens, so a mutation
        that deleted the hash comparison survived until this existed.
        """
        saved = B9J.SYSTEM_ABI_SOURCE_SHA256
        B9J.SYSTEM_ABI_SOURCE_SHA256 = "0" * 64
        self.addCleanup(lambda: setattr(B9J, "SYSTEM_ABI_SOURCE_SHA256", saved))
        with self.assertRaisesRegex(B9D.FreezeViolation, "must not be applied to another"):
            B9J.assert_abi_source_pinned()

    def test_the_pinned_table_covers_every_declared_variant_in_order(self):
        """Declaration order IS the wire tag, so a gap or a reorder is a decoding error waiting."""
        self.assertEqual(sorted(B9J.SYSTEM_INSTRUCTIONS), list(range(14)))
        self.assertEqual(B9J.SYSTEM_INSTRUCTIONS[0][0], "CreateAccount")
        self.assertEqual(B9J.SYSTEM_INSTRUCTIONS[2][0], "Transfer")
        self.assertEqual(B9J.SYSTEM_INSTRUCTIONS[13][0], "CreateAccountAllowPrefund")


class DecodeTests(unittest.TestCase):

    def test_the_observed_variants_decode_with_their_observed_lengths(self):
        """Lengths measured in the frozen artifact: 52, 36, 12, 4 and 12 respectively."""
        cases = {
            0: (encode(0, struct.pack("<QQ", 5, 165) + PUBKEY), 52,
                {"lamports": 5, "space": 165}),
            1: (encode(1, PUBKEY), 36, {}),
            2: (encode(2, struct.pack("<Q", 1_000_000)), 12, {"lamports": 1_000_000}),
            4: (encode(4), 4, {}),
            8: (encode(8, struct.pack("<Q", 165)), 12, {"space": 165}),
        }
        for tag, (data, expected_length, expected_fields) in cases.items():
            with self.subTest(tag=tag):
                self.assertEqual(len(data), expected_length,
                                 "fixture must match the length seen on chain")
                decoded = B9J.decode_system_instruction(data)
                self.assertEqual(decoded["tag"], tag)
                for key, value in expected_fields.items():
                    self.assertEqual(decoded["fields"][key], value)

    def test_a_seeded_creation_uses_a_u64_string_prefix(self):
        """bincode length-prefixes strings with u64. A 4-byte prefix would decode a wrong seed and
        then leave trailing bytes -- the artifact's 95..124 byte lengths are 92 + seed length."""
        seed = b"abc"
        data = encode(3, PUBKEY + struct.pack("<Q", len(seed)) + seed
                      + struct.pack("<QQ", 7, 165) + PUBKEY)
        self.assertEqual(len(data), 92 + len(seed))
        decoded = B9J.decode_system_instruction(data)
        self.assertEqual(decoded["name"], "CreateAccountWithSeed")
        self.assertEqual(decoded["fields"]["seed"], "abc")
        self.assertEqual(decoded["fields"]["lamports"], 7)

    def test_lamport_movement_distinguishes_none_from_zero(self):
        """A variant that cannot move lamports is not one that moved zero."""
        self.assertEqual(
            B9J.system_lamports_moved(B9J.decode_system_instruction(
                encode(2, struct.pack("<Q", 0)))), 0)
        self.assertIsNone(
            B9J.system_lamports_moved(B9J.decode_system_instruction(encode(8, struct.pack("<Q", 1)))))
        self.assertIsNone(
            B9J.system_lamports_moved(B9J.decode_system_instruction(encode(4))))


class RefusalTests(unittest.TestCase):

    def test_an_unknown_variant_tag_is_refused(self):
        """Including tags just past the pinned range, which a future ABI would add."""
        for tag in (14, 99, 2**32 - 1):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(B9D.FreezeViolation, "outside the pinned ABI"):
                    B9J.decode_system_instruction(encode(tag))

    def test_trailing_bytes_are_refused_not_treated_as_padding(self):
        """A payload that decodes and leaves data over is not the payload this ABI describes."""
        with self.assertRaisesRegex(B9D.FreezeViolation, "trailing byte"):
            B9J.decode_system_instruction(encode(2, struct.pack("<Q", 1) + bytes([0])))

    def test_truncated_payloads_are_refused(self):
        for data in (bytes([2, 0, 0]), encode(2, bytes([1, 2])), encode(0, PUBKEY)):
            with self.subTest(length=len(data)):
                with self.assertRaises(B9D.FreezeViolation):
                    B9J.decode_system_instruction(data)

    def test_a_seed_length_that_overruns_the_buffer_is_refused(self):
        """A declared length is a claim about the buffer, and must be checked against it."""
        data = encode(3, PUBKEY + struct.pack("<Q", 10_000) + b"abc")
        with self.assertRaisesRegex(B9D.FreezeViolation, "declares 10000 bytes"):
            B9J.decode_system_instruction(data)

    def test_pinned_but_unobserved_variants_still_decode_rather_than_being_dropped(self):
        """Absence from the artifact is not impossibility.

        Eight of the fourteen variants do not appear in the frozen population. A decoder that
        handled only what it had seen would under-count exactly the lamports it exists to find the
        first time one occurs.
        """
        withdraw = B9J.decode_system_instruction(encode(5, struct.pack("<Q", 42)))
        self.assertEqual(withdraw["name"], "WithdrawNonceAccount")
        self.assertEqual(B9J.system_lamports_moved(withdraw), 42)

        seed = b"s"
        transfer_with_seed = B9J.decode_system_instruction(
            encode(11, struct.pack("<Q", 9) + struct.pack("<Q", len(seed)) + seed + PUBKEY))
        self.assertEqual(transfer_with_seed["name"], "TransferWithSeed")
        self.assertEqual(B9J.system_lamports_moved(transfer_with_seed), 9)


if __name__ == "__main__":
    unittest.main()
