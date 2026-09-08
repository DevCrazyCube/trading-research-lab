"""Negative controls for the new forensic label audit."""
import unittest

from scripts.birth_origin import Refused
from scripts.memecoin_information_audit import lp_burn_amount


class LpBurnTests(unittest.TestCase):
    def instruction(self, tag=8, amount=123, **changes):
        data = bytes([tag]) + amount.to_bytes(8, "little")
        if tag == 15:
            data += bytes([9])
        return {"program_id": "token-program", "accounts": ["account", "lp-mint", "authority"],
                "data": data, **changes}

    def test_exact_burn_and_burn_checked(self):
        for tag in (8, 15):
            self.assertEqual(lp_burn_amount(self.instruction(tag), "lp-mint", "token-program"), 123)

    def test_other_tokens_burn_is_not_lp_evidence(self):
        self.assertIsNone(lp_burn_amount(self.instruction(), "different-mint", "token-program"))

    def test_wrong_program_is_not_evidence(self):
        self.assertIsNone(lp_burn_amount(self.instruction(), "lp-mint", "wrong-program"))

    def test_transfer_is_not_burn(self):
        self.assertIsNone(lp_burn_amount(self.instruction(3), "lp-mint", "token-program"))

    def test_truncated_and_padded_burn_refuse(self):
        for data in (b"\x08", b"\x08" + bytes(9), b"\x0f" + bytes(8), b"\x0f" + bytes(10)):
            with self.assertRaises(Refused):
                lp_burn_amount(self.instruction(data=data), "lp-mint", "token-program")

    def test_short_accounts_are_not_evidence(self):
        self.assertIsNone(lp_burn_amount(self.instruction(accounts=["account", "lp-mint"]),
                                        "lp-mint", "token-program"))

    def test_zero_burn_is_not_invented_as_positive(self):
        self.assertEqual(lp_burn_amount(self.instruction(amount=0), "lp-mint", "token-program"), 0)


if __name__ == "__main__":
    unittest.main()
