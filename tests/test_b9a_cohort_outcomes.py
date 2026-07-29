"""Focused tests for the B9a outcome decoder.

B9a shipped without any, and its whole result rests on one struct offset: a wrong `complete`
offset produces a plausible boolean rather than an error, so the base rate would be wrong in a
way nothing downstream could notice.

The synthetic account here is built **from the IDL field list**, not from the script's hardcoded
`struct` format. So the test derives the layout independently and the comparison is a genuine
re-decode rather than a restatement of the same constant. `test_transposed_layout_is_detected`
exists to show the instrument can FAIL — a decoder test that cannot fail proves nothing.

The invariant tests at the end pin the properties that actually validated the published run
(`agent_discussion.md` Seq 178): Borsh is unpadded, `complete` is the byte immediately after five
u64s, and the curve's state is one-dimensional in `real_quote_reserves`.
"""
import base64
import importlib.util
import json
import pathlib
import sqlite3
import struct
import sys
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "b9a", ROOT / "scripts" / "b9a_cohort_outcomes.py")
B9A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9A)

IDL = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
CURVE_FIELDS = next(t for t in IDL["types"] if t["name"] == "BondingCurve")["type"]["fields"]
DISCRIMINATOR = bytes(next(a for a in IDL["accounts"]
                           if a["name"] == "BondingCurve")["discriminator"])

# Launch constants for a SOL-quoted pump curve, confirmed against all 159 never-traded
# non-Mayhem members of the published cohort.
VT0, VQ0, RT0 = 1_073_000_000_000_000, 30_000_000_000, 793_100_000_000_000


def encode_curve(values, discriminator=DISCRIMINATOR, order=None):
    """Serialise a BondingCurve the way Borsh does: field order from the IDL, no padding."""
    out = bytearray(discriminator)
    for field in (order or CURVE_FIELDS):
        name, kind = field["name"], field["type"]
        value = values[name]
        if kind == "u64":
            out += struct.pack("<Q", value)
        elif kind == "bool":
            out += struct.pack("<?", value)
        elif kind == "pubkey":
            out += bytes(value)
        else:                                            # pragma: no cover - layout drift
            raise AssertionError(f"unhandled IDL type {kind!r} for {name!r}")
    return bytes(out)


def account(values, owner=B9A.PUMP, **kwargs):
    return {"data": [base64.b64encode(encode_curve(values, **kwargs)).decode(), "base64"],
            "owner": owner, "lamports": 1_000_000}


def curve_values(**overrides):
    base = {"virtual_token_reserves": VT0, "virtual_quote_reserves": VQ0,
            "real_token_reserves": RT0, "real_quote_reserves": 0,
            "token_total_supply": 1_000_000_000_000_000, "complete": False,
            "creator": bytes([7]) * 32, "is_mayhem_mode": False,
            "is_cashback_coin": False, "quote_mint": bytes([11]) * 32}
    base.update(overrides)
    return base


class DecodeLayout(unittest.TestCase):
    def test_every_decoded_field_round_trips(self):
        """Distinct values per field, so any transposition changes at least one result."""
        values = curve_values(virtual_token_reserves=111, virtual_quote_reserves=222,
                              real_token_reserves=333, real_quote_reserves=444,
                              token_total_supply=555, complete=True)
        decoded = B9A.decode_curve(account(values))
        for name in ("virtual_token_reserves", "virtual_quote_reserves", "real_token_reserves",
                     "real_quote_reserves", "token_total_supply"):
            self.assertEqual(decoded[name], values[name], name)
        self.assertIs(decoded["complete"], True)

    def test_complete_false_is_not_confused_with_a_neighbouring_byte(self):
        """`complete` sits between token_total_supply and creator; both must not leak into it."""
        decoded = B9A.decode_curve(account(curve_values(
            token_total_supply=0xFFFFFFFFFFFFFFFF, complete=False, creator=bytes([0xFF]) * 32)))
        self.assertIs(decoded["complete"], False)
        self.assertEqual(decoded["token_total_supply"], 0xFFFFFFFFFFFFFFFF)

    def test_borsh_layout_is_unpadded(self):
        """41 bytes for 5*u64 + bool. Native alignment would pad to 48 and shift `complete`."""
        self.assertEqual(B9A.CURVE_STRUCT.size, 41)
        self.assertEqual(len(encode_curve(curve_values())), 8 + 41 + 32 + 1 + 1 + 32)

    def test_transposed_layout_is_detected(self):
        """The decoder must FAIL on a wrong layout, or its passing says nothing."""
        swapped = list(CURVE_FIELDS)
        swapped[2], swapped[3] = swapped[3], swapped[2]   # real_token <-> real_quote
        values = curve_values(real_token_reserves=333, real_quote_reserves=444)
        decoded = B9A.decode_curve(account(values, order=swapped))
        self.assertNotEqual(decoded["real_quote_reserves"], 444)

    def test_idl_field_order_matches_the_hardcoded_struct(self):
        self.assertEqual([f["name"] for f in CURVE_FIELDS][:6],
                         ["virtual_token_reserves", "virtual_quote_reserves",
                          "real_token_reserves", "real_quote_reserves",
                          "token_total_supply", "complete"])
        self.assertEqual(B9A.CURVE_DISCRIMINATOR, DISCRIMINATOR)


class DecodeRefusals(unittest.TestCase):
    def test_absent_account_is_none_not_a_falsy_curve(self):
        self.assertIsNone(B9A.decode_curve(None))

    def test_short_account_raises(self):
        short = {"data": [base64.b64encode(DISCRIMINATOR + b"\x00" * 8).decode(), "base64"],
                 "owner": B9A.PUMP, "lamports": 0}
        with self.assertRaisesRegex(ValueError, "too short"):
            B9A.decode_curve(short)

    def test_foreign_discriminator_raises(self):
        with self.assertRaisesRegex(ValueError, "not BondingCurve"):
            B9A.decode_curve(account(curve_values(), discriminator=bytes(range(8))))

    def test_foreign_owner_raises(self):
        with self.assertRaisesRegex(ValueError, "owned by"):
            B9A.decode_curve(account(curve_values(), owner="11111111111111111111111111111111"))


ARTIFACT = ROOT / "research" / "b9a_outcomes.sqlite"


@unittest.skipUnless(ARTIFACT.exists(), "published artifact not present")
class PublishedArtifactInvariants(unittest.TestCase):
    """Properties that must hold if the offsets were right — checked against the real run."""

    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(f"file:{ARTIFACT}?mode=ro", uri=True)

    def q(self, sql):
        return self.db.execute(sql).fetchall()

    def test_token_total_supply_is_the_same_constant_for_every_member(self):
        self.assertEqual(self.q("SELECT DISTINCT token_total_supply FROM outcome"),
                         [(1_000_000_000_000_000,)])

    def test_every_account_is_owned_by_the_pump_program(self):
        self.assertEqual(self.q("SELECT DISTINCT owner FROM outcome"), [(B9A.PUMP,)])

    def test_complete_is_exactly_equivalent_to_zero_real_token_reserves(self):
        """43/1558 with no exceptions — impossible if `complete` came from a wrong offset."""
        self.assertEqual(
            self.q("SELECT COUNT(*) FROM outcome WHERE complete != (real_token_reserves = 0)"),
            [(0,)])

    def test_non_mayhem_curve_state_is_one_dimensional_in_real_quote_reserves(self):
        """vqr = vqr0 + rqr and tokens-out agree between the virtual and real sides.

        This is what makes F2 a statement about the curve's state *now* and not about its path:
        a full round-trip returns every field to its launch value.
        """
        rows = self.q(
            "SELECT virtual_token_reserves, virtual_quote_reserves, real_token_reserves,"
            " real_quote_reserves FROM outcome WHERE complete = 0 AND is_mayhem_mode = 0"
            f" AND quote_mint = '{B9A.SOL_SENTINEL}'")
        self.assertGreater(len(rows), 1000)
        for vt, vq, rt, rq in rows:
            self.assertEqual(vq, VQ0 + rq)
            self.assertEqual(VT0 - vt, RT0 - rt)

    def _curves(self, mayhem):
        return self.q(
            "SELECT virtual_token_reserves, virtual_quote_reserves, real_quote_reserves,"
            " real_token_reserves FROM outcome"
            f" WHERE complete = 0 AND is_mayhem_mode = {mayhem}"
            f" AND quote_mint = '{B9A.SOL_SENTINEL}'")

    def test_trading_conserves_the_constant_product_for_every_non_mayhem_curve(self):
        """Premise 1 of F5: k never moves on its own. 1,110/1,110, no exceptions."""
        k0 = VT0 * VQ0
        off = [1 for vt, vq, _, _ in self._curves(0) if abs(vt * vq - k0) > 0.01 * k0]
        self.assertEqual(off, [], f"{len(off)} non-Mayhem curves left the launch product")

    def test_mayhem_curves_launch_at_the_same_canonical_parameters(self):
        """Premise 2 of F5, and the one that makes it an argument rather than a correlation.

        Exactly two Mayhem curves sit at the canonical product, and both are untouched — 1 and 3
        lamports of real quote, virtual and real token reserves still exactly at launch. Mayhem
        curves therefore *start* where non-Mayhem curves start, so the others did not begin
        somewhere else; they moved.
        """
        k0 = VT0 * VQ0
        at_canonical = [(vq, rq, vt, rt) for vt, vq, rq, rt in self._curves(1)
                        if abs(vt * vq - k0) <= 0.01 * k0]
        self.assertEqual(len(at_canonical), 2)
        for vq, rq, vt, rt in at_canonical:
            self.assertLessEqual(rq, 3)                  # dust, never meaningfully traded
            self.assertEqual((vt, rt), (VT0, RT0))       # still exactly at launch
            self.assertEqual(vq, VQ0 + rq)

    def test_almost_every_traded_mayhem_curve_has_left_the_launch_product(self):
        """Conclusion of F5: 425/427, spanning 0.0006x to 33.8x of k0.

        Trading cannot do this (premise 1) and they did not start elsewhere (premise 2), so the
        virtual parameters were changed outside trading — `set_mayhem_virtual_params`, B7a F44.
        """
        k0 = VT0 * VQ0
        rows = self._curves(1)
        ratios = [vt * vq / k0 for vt, vq, _, _ in rows]
        off = [r for r in ratios if abs(r - 1) > 0.01]
        self.assertEqual((len(off), len(rows)), (425, 427))
        self.assertLess(min(ratios), 0.001)              # k driven far below launch
        self.assertGreater(max(ratios), 30)              # and far above it


if __name__ == "__main__":
    unittest.main()
